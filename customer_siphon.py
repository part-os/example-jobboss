import jobboss.models as jb
from paperless.objects.customers import (Account as PPAccount, Contact as PPContact, AccountList as PPAccountList,
                                         ContactList as PPContactList)
from common import logger


def get_payment_terms_period(terms):
    if terms is not None:
        if '30' in terms:
            return 30
        elif '45' in terms:
            return 45
        elif '60' in terms:
            return 60
        elif '90' in terms:
            return 90
        else:
            return 0
    return 0


def parse_names(full_name):
    names_array = []
    if full_name:
        names_array = full_name.split()
    if len(names_array) == 1:
        return full_name, None
    elif len(names_array) > 1:
        return full_name[0], full_name[1:]
    return None, None

def get_jb_address(address_code):
    addr_obj = jb.Address.objects.filter(address=address_code).last()
    # TODO Build out address record first and then associate it with the contact
    if addr_obj:
        full_address = f'{addr_obj.line1} {addr_obj.line2} {addr_obj.state}'
    return None


def import_customers():

    jb_customers = jb.Customer.objects.all()[0:10]
    logger.info(f'Found {len(jb_customers)} customers in the Customer table.')

    jb_contacts = jb.Contact.objects.all()[0:10]
    logger.info(f'Found {len(jb_contacts)} customers in the Contact table.')

    accounts_created = 0
    contacts_created = 0
    erp_code_to_pp_account_mapping = {}
    account_creation_errors = []

    # Iterate through customers and parse information into Paperless Account format
    for customer in jb_customers:
        # Required fields:
        business_name = customer.name
        # Optional fields:
        erp_code = customer.customer
        credit_line = customer.credit_limit
        notes = customer.note_text
        payment_terms = customer.terms
        payment_terms_period = get_payment_terms_period(payment_terms)
        if payment_terms_period == 0:
            payment_terms_period = 1  # TODO - remove this once we remove the constraint in the open API that payment_terms_period must be non-null and also > 0
        phone = None  # No phone field on Customers in jb
        phone_ext = None  # No phone_ext field on Customers in jb
        purchase_orders_enabled = bool(customer.accept_bo)
        tax_exempt = False  # No tax exemption options on Customers in jb
        tax_rate = None  # No tax rate field on Customers in jb
        url = customer.url

        pp_account = PPAccount(
            name=business_name,
            credit_line=credit_line,
            erp_code=erp_code,
            notes=notes,
            payment_terms=payment_terms,
            payment_terms_period=payment_terms_period,
            phone=phone,
            phone_ext=phone_ext,
            purchase_orders_enabled=purchase_orders_enabled,
            tax_exempt=tax_exempt,
            tax_rate=tax_rate,
            url=url
        )

        try:
            pp_account.create()
            erp_code_to_pp_account_mapping[erp_code] = pp_account
            accounts_created += 1
            pp_account_created = True
        except Exception as e:
            logger.info(f'Encountered an error importing account: {business_name} - skipping.')
            pp_account_created = False
            account_creation_errors.append(f'{erp_code} | {str(e)}')

        # if pp_account_created:
            # print(erp_code_to_pp_account_mapping)

    count = 0
    for contact in jb_contacts:
        email = contact.email_address
        first_name, last_name = parse_names(contact.contact_name)
        # address = get_jb_address(contact.address)
        # notes =,
        # phone =,
        # phone_ext =,
        count += 1
        if not email or not first_name or not last_name:
            pp_contact = PPContact(
                account_id=count,
                email=email,
                first_name=first_name,
                last_name=last_name,
                # address=,
                # notes=,
                # phone=,
                # phone_ext=,
            )

            try:
                pp_contact.create()
                contacts_created += 1
                pp_account_created = True
            except Exception as e:
                logger.info(f'Encountered an error importing account: {pp_contact.email} - skipping.')
                pp_account_created = False
                account_creation_errors.append(f'{pp_contact.email} | {str(e)}')

    write_errors_to_file('account_creation_errors.txt', account_creation_errors)


def write_errors_to_file(file_path, error_identifiers):
    with open(file_path, 'w') as f:
        for error_identifier in error_identifiers:
            f.write(f'{error_identifier}\n')


def delete_all_accounts_and_contacts():
    # Get a list of all the Paperless Parts accounts
    accounts_list = PPAccountList.list()
    num_accounts = len(accounts_list)
    logger.info(f'{num_accounts} accounts detected in Paperless Parts.')

    # Delete the accounts one at a time. This will cascade delete any records associated with the account, including
    # address information and contacts
    for i, brief_account in enumerate(accounts_list):
        if i % 50 == 0:
            logger.info(f'Deleting account {i+1}/{num_accounts}')
        account = PPAccount(id=brief_account.id, name=brief_account.name)
        account.delete()

    # Get a list of all the remaining contacts
    contacts_list = PPContactList.list()
    num_contacts = len(contacts_list)
    logger.info(f'{num_contacts} contacts detected in Paperless Parts.')

    # Delete the contacts one at a time
    for i, brief_contact in enumerate(contacts_list):
        if i % 50 == 0:
            logger.info(f'Deleting contact {i+1}/{num_contacts}')
        contact = PPContact(
            id=brief_contact.id,
            account_id=brief_contact.account_id,
            email=brief_contact.email,
            first_name=brief_contact.first_name,
            last_name=brief_contact.last_name
        )
        contact.delete()
