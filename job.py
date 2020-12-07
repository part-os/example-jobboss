import attr
import datetime
import uuid
from itertools import chain
from common import logger
import common
from paperless.objects.components import Operation
from paperless.objects.orders import Order, OrderComponent
import jobboss.models as jb
from jobboss.query.customer import get_or_create_customer, \
    get_or_create_contact, get_or_create_address
from jobboss.query.job import get_material, AssemblySuffixCounter
from routing import generate_routing_lines


def safe_round(f):
    try:
        return round(f, 2)
    except TypeError:
        return f


def process_order(order: Order):
    paperless_user = common.JOBBOSS_CONFIG.paperless_user \
        if common.JOBBOSS_CONFIG.paperless_user else None
    sales_code = common.JOBBOSS_CONFIG.sales_code
    import_material = common.JOBBOSS_CONFIG.import_material
    default_location = common.JOBBOSS_CONFIG.default_location \
        if common.JOBBOSS_CONFIG.default_location else None
    import_operations = common.JOBBOSS_CONFIG.import_operations

    logger.info('Processing order {}'.format(order.number))
    # get customer, bill to info, ship to info
    if order.customer.company:
        business_name = order.customer.company.business_name
        code = order.customer.company.erp_code
    else:
        business_name = '{}, {}'.format(order.customer.last_name,
                                        order.customer.first_name)
        code = None
    customer: jb.Customer = get_or_create_customer(business_name, code)
    bill_name = '{} {}'.format(order.billing_info.first_name,
                               order.billing_info.last_name)
    contact: jb.Contact = get_or_create_contact(customer, bill_name)
    bill_to: jb.Address = get_or_create_address(
        customer,
        attr.asdict(order.billing_info),
        is_shipping=False
    )
    contact.address = bill_to.address
    contact.save()
    ship_to: jb.Address = get_or_create_address(
        customer,
        attr.asdict(order.shipping_info),
        is_shipping=True
    )

    now = datetime.datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    ship_str = order.shipping_option.summary(
        order.ships_on_dt, order.payment_details.payment_type) if order.shipping_option is not None else ''

    terms = order.payment_details.payment_terms.upper() \
                if order.payment_details.payment_type == 'purchase_order' \
                else 'Credit Card'
    if order.payment_details.payment_type == 'purchase_order' and \
            customer.terms:
        terms = customer.terms
    notes = 'PP Quote #{}'.format(order.quote_number)
    if order.private_notes:
        notes += '\r\n\r\n{}'.format(order.private_notes)
    commission_pct = 0
    employee = None
    if customer.sales_rep:
        qs = jb.Employee.objects.filter(employee=customer.sales_rep)
        employee = qs.first()
        if employee:
            commission_pct = employee.commission_pct

    so_header = jb.SoHeader(
        customer=customer.customer,
        ship_to=ship_to.address,
        contact=contact.contact,
        order_taken_by=paperless_user,
        ship_via=customer.ship_via,
        terms=terms,
        sales_tax_amt=0,
        sales_tax_rate=0,
        order_date=today,
        promised_date=order.ships_on_dt,
        customer_po=order.payment_details.purchase_order_number[:20] if order.payment_details.purchase_order_number is not None else None,
        status='Open',
        total_price=order.payment_details.total_price.dollars,
        currency_conv_rate=1,
        trade_currency=1,
        fixed_rate=True,
        trade_date=today,
        note_text=notes,
        comment=ship_str,
        last_updated=now,
        source='System',
        prepaid_tax_amount=0,
        sales_rep=customer.sales_rep,
    )
    so_header.save_with_autonumber()
    logger.info('Created sales order {}'.format(so_header.sales_order))

    # create links to quote and order
    order_link = jb.Attachment(
        owner_type='SOHeader',
        owner_id=so_header.sales_order,
        attach_path='https://app.paperlessparts.com/orders/edit/{}'.format(
            order.number),
        description='PP Order #{}'.format(order.number),
        print_attachment=False,
        last_updated=now,
        attach_type='Link'
    )
    order_link.save_with_autonumber()

    quote_link = jb.Attachment(
        owner_type='SOHeader',
        owner_id=so_header.sales_order,
        attach_path='https://app.paperlessparts.com/quotes/edit/{}'.format(
            order.quote_number),
        description='PP Quote #{}'.format(order.quote_number),
        print_attachment=False,
        last_updated=now,
        attach_type='Link'
    )
    quote_link.save_with_autonumber()

    for i, order_item in enumerate(order.order_items):
        logger.debug('Starting order item {}'.format(i))
        top_level_job = None
        top_level_uuid = None
        suffix = AssemblySuffixCounter()
        comp_uuid = {}  # component ID -> JB object ID
        comp_job = {}  # component ID -> JB job instance

        # create jobs for each mfg component and assembly
        for assm_comp in order_item.iterate_assembly():
            comp: OrderComponent = assm_comp.component
            # skip hardware, add those components later
            if comp.is_hardware:
                continue
            if comp.description:
                if len(comp.description) <= 30:
                    desc = comp.description
                    ext_desc = None
                else:
                    desc = comp.description[0:30]
                    ext_desc = comp.description[30:]
            else:
                desc = None
                ext_desc = None

            # get or create material master
            if not comp.part_number:
                material_name = None
            elif import_material:
                material = get_material(comp.part_number)
                if material:
                    logger.info('Found matching material')
                    material_name = material.material
                else:
                    logger.info('Creating Material {}'.format(
                        comp.part_number))
                    material_name = comp.part_number

                    # calculate the standard cost as the sum of all operations
                    cost = 0
                    for op in chain(comp.material_operations, comp.shop_operations):
                        cost += op.cost.dollars
                    if order_item.quantity:
                        cost = cost / order_item.quantity
                    material = jb.Material.objects.create(
                        material=comp.part_number,
                        description=desc,
                        ext_description=ext_desc,
                        sales_code=sales_code,
                        rev=comp.revision,
                        location_id=default_location,
                        type='F',
                        status='Active',
                        pick_buy_indicator='P',
                        stocked_uofm='ea',
                        purchase_uofm='ea',
                        cost_uofm='ea',
                        price_uofm='ea',
                        selling_price=order_item.unit_price.dollars,
                        standard_cost=cost,
                        reorder_qty=0,
                        lead_days=0,
                        uofm_conv_factor=1,
                        lot_trace=False,
                        rd_whole_unit=False,
                        make_buy='M',
                        use_price_breaks=True,
                        last_updated=datetime.datetime.utcnow(),
                        taxable=False,
                        affects_schedule=True,
                        tooling=False,
                        isserialized=False,
                        objectid=uuid.uuid4()
                    )
                    material_name = material.material
            else:
                material_name = comp.part_number

            notes = []
            if order_item.public_notes:
                notes.append(order_item.public_notes)
            if order_item.private_notes:
                notes.append(order_item.private_notes)
            extras = comp.make_quantity - (order_item.quantity * comp.innate_quantity)
            job = jb.Job(
                sales_rep=employee,
                customer=customer,
                ship_to=ship_to.address,
                contact=contact.contact,
                terms=terms,
                sales_code=sales_code,
                type='Assembly' if len(comp.child_ids) else 'Regular',
                order_date=today,
                status='Active',
                status_date=today,
                part_number=material_name,
                rev=comp.revision,
                description=desc,
                ext_description=ext_desc,
                drawing=comp.part_number,
                build_to_stock=True,
                order_quantity=order_item.quantity,
                extra_quantity=extras,
                pick_quantity=0,
                make_quantity=comp.make_quantity,
                split_quantity=0,
                completed_quantity=0,
                shipped_quantity=0,
                fg_transfer_qty=0,
                returned_quantity=0,
                in_production_quantity=0,
                assembly_level=0,
                certs_required=False,
                time_and_materials=False,
                open_operations=0,
                scrap_pct=extras / comp.make_quantity * 100,
                est_scrap_qty=extras,
                est_rem_hrs=0,
                est_total_hrs=0,
                est_labor=0,
                est_material=0,
                est_service=0,
                est_labor_burden=0,
                est_machine_burden=0,
                est_ga_burden=0,
                act_revenue=0,
                act_scrap_quantity=0,
                act_total_hrs=0,
                act_labor=0,
                act_material=0,
                act_service=0,
                act_labor_burden=0,
                act_machine_burden=0,
                act_ga_burden=0,
                priority=5,
                unit_price=order_item.unit_price.dollars if comp.is_root_component else 0,
                total_price=order_item.unit_price.dollars * order_item.quantity if comp.is_root_component else 0,
                price_uofm='ea',
                currency_conv_rate=1,
                trade_currency=1,
                fixed_rate=True,
                trade_date=today,
                commission_pct=commission_pct,
                customer_po=order.payment_details.purchase_order_number[:20] if order.payment_details.purchase_order_number is not None else None,
                customer_po_ln=None,
                quantity_per=1,
                profit_pct=0,
                labor_markup_pct=0,
                mat_markup_pct=0,
                serv_markup_pct=0,
                labor_burden_markup_pct=0,
                machine_burden_markup_pct=0,
                ga_burden_markup_pct=0,
                lead_days=order_item.lead_days,
                profit_markup='M',
                prepaid_amt=0,
                split_to_job=False,
                note_text='\n\n'.join(notes),
                last_updated=now,
                order_unit='ea',
                price_unit_conv=1,
                source='System',
                plan_modified=False,
                objectid=str(uuid.uuid4()),
                prepaid_tax_amount=0,
                prepaid_trade_amt=0,
                commissionincluded=False,
                ship_via=customer.ship_via,
                top_lvl_job=top_level_job,
            )
            if comp.is_root_component:
                job.save_with_autonumber()
                top_level_job = job.job
                top_level_uuid = job.objectid
                suffix.get_suffix(0, 0, 1)
            else:
                job.job = top_level_job + suffix.get_suffix(
                    assm_comp.level,
                    assm_comp.level_index,
                    assm_comp.level_count
                )
            job.top_lvl_job = top_level_job
            job.save()
            comp_uuid[comp.id] = job.objectid
            comp_job[comp.id] = job
            logger.info('Created job {}'.format(job.job))

            # link the assembly
            if not comp.is_root_component:
                jb.BillOfJobs.objects.create(
                    parent_job=comp_job[assm_comp.parent.id],
                    component_job=job,
                    relationship_type='Component',
                    relationship_qty=comp.innate_quantity,
                    manual_link=False,
                    last_updated=now,
                    root_job=top_level_job,
                    objectid=str(uuid.uuid4()),
                    root_job_oid=top_level_uuid,
                    parent_job_oid=comp_uuid[assm_comp.parent.id],
                    component_job_oid=job.objectid
                )

            # create links to quote and order
            if comp.is_root_component:
                order_link = jb.Attachment(
                    owner_type='Job',
                    owner_id=job.job,
                    attach_path='https://app.paperlessparts.com/orders/edit/{}'.format(
                        order.number),
                    description='PP Order #{}'.format(order.number),
                    print_attachment=False,
                    last_updated=now,
                    attach_type='Link'
                )
                order_link.save_with_autonumber()

                quote_link = jb.Attachment(
                    owner_type='Job',
                    owner_id=job.job,
                    attach_path='https://app.paperlessparts.com/quotes/edit/{}'.format(
                        order.quote_number),
                    description='PP Quote #{}'.format(order.quote_number),
                    print_attachment=False,
                    last_updated=now,
                    attach_type='Link'
                )
                quote_link.save_with_autonumber()

            if comp.material:
                mat_name = comp.material.name.upper()
            else:
                mat_name = ''
            mat = jb.MaterialReq(
                job=job,
                description=mat_name[0:30],
                pick_buy_indicator='B',
                type='M',
                status='O',
                quantity_per_basis='I',
                quantity_per=0,
                uofm='ea',
                deferred_qty=0,
                est_qty=0,
                est_unit_cost=0,
                est_addl_cost=0,
                est_total_cost=0,
                act_qty=0,
                act_unit_cost=0,
                act_addl_cost=0,
                act_total_cost=0,
                part_length=0,
                part_width=0,
                bar_end=0,
                cutoff=0,
                facing=0,
                bar_length=0,
                lead_days=0,
                currency_conv_rate=1,
                trade_currency=1,
                fixed_rate=True,
                trade_date=today,
                certs_required=False,
                manual_link=False,
                last_updated=now,
                cost_uofm='ea',
                cost_unit_conv=1,
                quantity_multiplier=1,
                partial_res=False,
                objectid=uuid.uuid4(),
                job_oid=job.objectid,
                affects_schedule=False,
                rounded=True
            )
            mat.save()

            if comp.is_root_component:
                so_detail = jb.SoDetail(
                    sales_order=so_header,
                    so_line='{:03d}'.format(i + 1),
                    line=None,
                    material=material_name,
                    ship_to=ship_to.address,
                    drop_ship=False,
                    quote=None,
                    job=job.job,
                    status='Open',
                    make_buy='M',
                    unit_price=order_item.unit_price.dollars,
                    discount_pct=0,
                    price_uofm='ea',
                    total_price=order_item.total_price.dollars,
                    deferred_qty=0,
                    prepaid_amt=0,
                    unit_cost=order_item.unit_price.dollars,
                    order_qty=order_item.quantity,
                    stock_uofm='ea',
                    backorder_qty=0,
                    picked_qty=0,
                    shipped_qty=0,
                    returned_qty=0,
                    certs_required=False,
                    taxable=False,
                    commissionable=bool(commission_pct),
                    commission_pct=commission_pct,
                    sales_code=sales_code,
                    note_text='\n\n'.join(notes),
                    promised_date=order_item.ships_on_dt,
                    last_updated=now,
                    description=desc,
                    ext_description=ext_desc,
                    price_unit_conv=1,
                    rev=comp.revision,
                    cost_uofm='ea',
                    cost_unit_conv=1,
                    partial_res=False,
                    prepaid_trade_amt=0,
                    objectid=uuid.uuid4(),
                    commissionincluded=False
                )
                so_detail.save()
                so_detail.refresh_from_db()

                delivery = jb.Delivery(
                    so_detail=so_detail.so_detail,
                    requested_date=order_item.ships_on_dt,
                    promised_date=order_item.ships_on_dt,
                    promised_quantity=order_item.quantity,
                    shipped_quantity=0,
                    remaining_quantity=order_item.quantity,
                    returned_quantity=0,
                    ncp_quantity=0,
                    comment='\n\n'.join(notes),
                    last_updated=now,
                    objectid=str(uuid.uuid4()),
                )
                delivery.save_with_autonumber()
                logger.info('Created delivery {}'.format(delivery.delivery))

            # now insert routing for operations
            if import_operations:
                operations_list = comp.shop_operations
                if comp.is_root_component:
                    operations_list = operations_list + order_item.ordered_add_ons
                j = -1
                for op in operations_list:
                    runtime = 0
                    setup_time = 0
                    notes = None
                    if isinstance(op, Operation):
                        runtime = op.runtime if op.runtime is not None else 0
                        setup_time = op.setup_time if op.setup_time is not None else 0
                        notes = op.notes
                    routing_lines = list(generate_routing_lines(op.name))
                    for k, routing_line in enumerate(routing_lines):
                        j += 1
                        logger.debug('Creating operation {}'.format(j))
                        job_op = jb.JobOperation(
                            job=job,
                            sequence=j,
                            description=op.name[0:25] if op.name else op.name,
                            priority=5,
                            run_method='Min/Part',
                            run=runtime * 60,
                            est_run_per_part=runtime,
                            efficiency_pct=100,
                            attended_pct=100,
                            queue_hrs=0,
                            est_total_hrs=comp.make_quantity * runtime + setup_time,
                            est_setup_hrs=setup_time,
                            est_run_hrs=runtime * comp.make_quantity,
                            est_setup_labor=0,
                            est_run_labor=0,
                            est_labor_burden=0,
                            est_machine_burden=0,
                            est_ga_burden=0,
                            est_required_qty=comp.make_quantity,
                            est_unit_cost=0,
                            est_addl_cost=0,
                            est_total_cost=0,
                            deferred_qty=comp.make_quantity,
                            act_setup_hrs=0,
                            act_run_hrs=0,
                            act_run_qty=0,
                            act_scrap_qty=0,
                            act_setup_labor=0,
                            act_run_labor=0,
                            act_labor_burden=0,
                            act_machine_burden=0,
                            act_ga_burden=0,
                            act_unit_cost=0,
                            act_addl_cost=0,
                            act_total_cost=0,
                            setup_pct_complete=0,
                            run_pct_complete=0,
                            rem_run_hrs=runtime * comp.make_quantity,
                            rem_setup_hrs=setup_time,
                            rem_total_hrs=comp.make_quantity * runtime + setup_time,
                            overlap=0,
                            overlap_qty=0,
                            est_ovl_hrs=0,
                            lead_days=0,
                            schedule_exception_old=False,
                            status='O',
                            minimum_chg_amt=0,
                            cost_unit_conv=0,
                            currency_conv_rate=1,
                            fixed_rate=True,
                            rwk_quantity=0,
                            rwk_setup_hrs=0,
                            rwk_run_hrs=0,
                            rwk_setup_labor=0,
                            rwk_run_labor=0,
                            rwk_labor_burden=0,
                            rwk_machine_burden=0,
                            rwk_ga_burden=0,
                            rwk_scrap_qty=0,
                            note_text=notes,
                            last_updated=now,
                            act_run_labor_hrs=0,
                            setup_qty=0,
                            run_qty=0,
                            rwk_run_labor_hrs=0,
                            rwk_setup_qty=0,
                            rwk_run_qty=0,
                            act_setup_labor_hrs=0,
                            rwk_setup_labor_hrs=0,
                            objectid=str(uuid.uuid4()),
                            job_oid=job.objectid,
                            sched_resources=1,
                            lag_hours=0,
                            manual_start_lock=False,
                            manual_stop_lock=False,
                            priority_zero_lock=False,
                            firm_zone_lock=False,
                            sb_runmethod=None,
                        )
                        if not routing_line.is_inside:
                            # outside service
                            job_op.inside_oper = False
                            job_op.vendor = routing_line.vendor_instance
                            job_op.wc_vendor = routing_line.vendor_instance.vendor
                            job_op.operation_service = routing_line.service[0:10] \
                                if routing_line.service else routing_line.service
                            job_op.cost_unit = 'ea'
                            job_op.cost_unit_conv = 1
                            job_op.trade_currency = 1
                            job_op.trade_date = today
                            if comp.deliver_quantity:
                                job_op.est_unit_cost = safe_round(
                                    op.cost.dollars / comp.deliver_quantity)
                            job_op.est_total_cost = safe_round(op.cost.dollars)
                            job_op.act_run_qty = comp.make_quantity
                        else:
                            # inside operation
                            job_op.inside_oper = True
                            job_op.work_center = routing_line.work_center_instance
                            job_op.wc_vendor = routing_line.work_center_instance.work_center
                            if routing_line.has_operation:
                                job_op.operation_service = routing_line.operation[0:10]
                                job_op.note_text = routing_line.operation_instance.note_text
                            job_op.workcenter_oid = routing_line.work_center_instance.objectid
                            job_op.queue_hrs = routing_line.work_center_instance.queue_hrs
                        try:
                            job_op.save()
                        except:
                            logger.error('Could not save operation')
                            logger.error(job_op.__dict__)
                            raise
                        logger.info('Saved operation {} {} {}'.format(
                            j, job_op.work_center, job_op.vendor))

        # add hardware items as MaterialReqs
        comp: OrderComponent
        for comp in order_item.components:
            if not comp.is_hardware:
                continue
            material = get_material(comp.part_number)
            if material:
                logger.info('Found matching hardware material')
                material_name = material.material
            else:
                if import_material:
                    logger.info('Creating hardware Material {}'.format(
                        comp.part_number))
                    material = jb.Material.objects.create(
                        material=comp.part_number,
                        description=comp.description[0:30] if comp.description else None,
                        sales_code=sales_code,
                        rev=comp.revision,
                        location_id=default_location,
                        type='H',
                        status='Active',
                        pick_buy_indicator='B',
                        stocked_uofm='ea',
                        purchase_uofm='ea',
                        cost_uofm='ea',
                        price_uofm='ea',
                        standard_cost=0.0,
                        reorder_qty=0,
                        lead_days=0,
                        uofm_conv_factor=1,
                        lot_trace=False,
                        rd_whole_unit=False,
                        make_buy='B',
                        use_price_breaks=True,
                        last_updated=datetime.datetime.utcnow(),
                        taxable=False,
                        affects_schedule=False,
                        tooling=False,
                        isserialized=False,
                        objectid=uuid.uuid4()
                    )
                    material_name = material.material
                else:
                    material_name = comp.part_number
                    logger.info('No hardware material for {}'.format(
                        comp.part_number))

            for parent_id in comp.parent_ids:
                job = comp_job[parent_id]
                qty_per = None
                parent = order_item.get_component(parent_id)
                for child in parent.children:
                    if child.child_id == comp.id:
                        qty_per = child.quantity
                        break
                jb.MaterialReq.objects.create(
                    job=job,
                    material=material_name,
                    description=comp.description[0:30] if comp.description else material_name,
                    pick_buy_indicator='B',
                    type='H',
                    status='O',
                    quantity_per_basis='I',
                    quantity_per=qty_per,
                    uofm='ea',
                    deferred_qty=0,
                    est_qty=comp.make_quantity,
                    est_unit_cost=0,
                    est_addl_cost=0,
                    est_total_cost=0,
                    act_qty=0,
                    act_unit_cost=0,
                    act_total_cost=0,
                    part_length=0,
                    part_width=0,
                    bar_end=0,
                    facing=0,
                    bar_length=0,
                    lead_days=0,
                    currency_conv_rate=1,
                    trade_currency=1,
                    fixed_rate=1,
                    trade_date=today,
                    certs_required=0,
                    manual_link=1,
                    last_updated=now,
                    cost_uofm='ea',
                    cost_unit_conv=1,
                    quantity_multiplier=1,
                    partial_res=0,
                    objectid=str(uuid.uuid4()),
                    job_oid=job.objectid,
                    affects_schedule=0,
                    material_oid=material.objectid if material else None,
                    rounded=1,
                )
