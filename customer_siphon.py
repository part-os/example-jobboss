import jobboss.models as jb
from paperless.objects.customers import (Company as PPAccount, Customer as PPContact, AddressInfo as PPAddressInfo,
                                         CompanyList as PPAccountList, CustomerList as PPContactList)
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


def import_customers():

    jb_customers = jb.Customer.objects.all()[0:10]
    logger.info(f'Found {len(jb_customers)} customers in the Customer table.')

    jb_contacts = jb.Contact.objects.all()[0:10]
    logger.info(f'Found {len(jb_contacts)} customers in the Contact table.')

    accounts_created = 0
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
            business_name=business_name,
            credit_line=credit_line,
            erp_code=erp_code,
            notes=notes,
            # payment_terms=payment_terms,
            # payment_terms_period=payment_terms_period,
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

        if pp_account_created:
            print(pp_account)


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
        account = PPAccount(id=brief_account.id, business_name=brief_account.business_name)
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
            company_id=brief_contact.company_id,
            email=brief_contact.email,
            first_name=brief_contact.first_name,
            last_name=brief_contact.last_name
        )
        contact.delete()
