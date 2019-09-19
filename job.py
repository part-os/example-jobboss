import attr
import datetime
import uuid
from itertools import chain
from common import logger, JOBBOSS_CONFIG
from paperless.objects.orders import Order
import jobboss.models as jb
from jobboss.query.customer import get_or_create_customer, \
    get_or_create_contact, get_or_create_address
from jobboss.query.job import get_material, get_work_center, \
    get_default_work_center

PAPERLESS_USER = JOBBOSS_CONFIG.paperless_user \
    if JOBBOSS_CONFIG.paperless_user else None
SALES_CODE = JOBBOSS_CONFIG.sales_code
IMPORT_MATERIAL = JOBBOSS_CONFIG.import_material
DEFAULT_LOCATION = JOBBOSS_CONFIG.default_location \
    if JOBBOSS_CONFIG.default_location else None
IMPORT_OPERATIONS = JOBBOSS_CONFIG.import_operations


def get_wc(name):
    wc = get_work_center(name)
    if wc is None:
        return get_default_work_center()
    else:
        return wc


def process_order(order: Order):
    logger.info('Processing order {}'.format(order.number))
    # get customer, bill to info, ship to info
    if order.customer.company:
        business_name = order.customer.company.business_name
    else:
        business_name = '{}, {}'.format(order.customer.last_name,
                                        order.customer.first_name)
    customer: jb.Customer = get_or_create_customer(business_name)
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
        order.ships_on_dt, order.payment_details.payment_type)

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
        order_taken_by=PAPERLESS_USER,
        ship_via=customer.ship_via,
        terms=terms,
        sales_tax_amt=0,
        sales_tax_rate=0,
        order_date=today,
        promised_date=order.ships_on_dt,
        customer_po=order.payment_details.purchase_order_number,
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

        comp = order_item.components[0]

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
        elif IMPORT_MATERIAL:
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
                    sales_code=SALES_CODE,
                    rev=comp.revision,
                    location_id=DEFAULT_LOCATION,
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
        job = jb.Job(
            sales_rep=employee,
            customer=customer,
            ship_to=ship_to.address,
            contact=contact.contact,
            terms=terms,
            sales_code=SALES_CODE,
            type='Regular',
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
            extra_quantity=0,
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
            scrap_pct=(comp.make_quantity - order_item.quantity) / comp.make_quantity * 100,
            est_scrap_qty=comp.make_quantity - order_item.quantity,
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
            unit_price=order_item.unit_price.dollars,
            total_price=order_item.unit_price.dollars * order_item.quantity,
            price_uofm='ea',
            currency_conv_rate=1,
            trade_currency=1,
            fixed_rate=True,
            trade_date=today,
            commission_pct=commission_pct,
            customer_po=order.payment_details.purchase_order_number,
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
        )
        job.save_with_autonumber()
        job.top_lvl_job = job.job
        job.save()
        logger.info('Created job {}'.format(job.job))

        # create links to quote and order
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
            sales_code=SALES_CODE,
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
        if IMPORT_OPERATIONS:
            for j, op in enumerate(comp.shop_operations):
                runtime = op.runtime if op.runtime is not None else 0
                setup_time = op.setup_time if op.setup_time is not None else 0
                logger.debug('Creating operation {}'.format(j))
                job_op = jb.JobOperation(
                    job=job,
                    sequence=j,
                    description=op.name,
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
                    deferred_qty=0,
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
                    note_text=op.notes,
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
                )
                job_op.inside_oper = True
                wc = get_wc(op.name)
                job_op.work_center = wc
                job_op.workcenter_oid = wc.objectid
                job_op.wc_vendor = job_op.work_center.work_center
                job_op.queue_hrs = job_op.work_center.queue_hrs
                job_op.save()
                logger.info('Saved operation {} {} {}'.format(
                    j, job_op.work_center, job_op.vendor))
