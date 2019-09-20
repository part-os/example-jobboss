Part OS Example JobBOSS Connector
=================================

Clone and customize this skeleton to quickly integrate your Paperless Parts account with an on-premise JobBOSS installation.

Paperless Parts/JobBOSS Integration
-----------------------------------

Run this connector at regular intervals to monitor your Paperless Parts account for new orders and to import that order information into your JobBOSS ERP system. This connector will import or link to data in the following tables/modules:

* Customers
* Materials
* Sales Orders
* Jobs

Installation
------------

### Prerequisites

These instructions assume you will run the connector on a Windows 10 computer or virtual machine.

First install the latest [Python3](https://www.python.org/downloads/), which
includes `python3`, `pip`, and `venv`. Add the Python installation folder to
your system path.

Next create a folder for your project. In these instructions, we will assume your folder is `C:\partos`. In this folder, clone this repository using [Git for Windows](https://git-scm.com/download/win).

The repository contains an installation script that will initialize submodules, create a virtual environment, and install all dependencies. Run `install.bat` from the command line to install the connector.

### Configure the Connector

Your shop-specific settings, including authentication credentials and configuration options, are stored in a single file. For security, you should never check this file into a version control system, like git. (Here's a [good blog post](https://johnresig.com/blog/keeping-passwords-in-source-control/) describing why.)

An example configuration file (without any sensitive data) can be found in `config.example.ini`. Copy this file to `config.ini` and edit it using a text editor, like Notepad.

You will need to provide real values for these options, which are divided into two categories.

`[Paperless]`

* `active`: set to 0 to disable the connector; otherwise keep this at 1
* `slug`: provided by Paperless Parts support, this is a version of your company's name, such as `my-company-name`
* `token`: provided by Paperless Parts support, this grants the connector access to your account; protect this token like you would protect a password
* `logpath`: the filename and location to store log files; these will help you diagnose any issues with order import

`[JobBOSS]`

* `host`: the server name or IP address of your JobBOSS MS SQL Server
* `name`: the name of the MS SQL Server database
* `user`: MS SQL Server username; leave this blank if you use LDAP authentication
* `password`: MS SQL Server password; leave this blank if you use LDAP authentication
* `paperless_user`: username to use for the "Order Taken By" field; a user with this name must exist in JobBOSS; we suggest creating a user named `PPRLSS`; you can leave this blank
* `sales_code`: sales code to be used when creating materials, jobs, and sales orders
* `import_material`: set to 1 to link a material (i.e., part number) to jobs and sales orders; set to 0 to populate a part number but not link to a material
* `default_location`: location to be specified for newly created materials; ignored if `import_material` is 0
* `import_operations`: set to 1 to add routing to jobs, linking Paperless Parts operation name to JobBOSS work center when possible; otherwise set to 0

### Schedule the Connector to Run

On a Windows 10 system, the easiest way to run the connector at regular intervals is to use the built-in Task Scheduler. In Task Scheduler, create a new task for your connector. We suggest the following configuration:

* Name: Paperless Parts Connector
* Security options: Run whether user is logged in or not
* Trigger: One time (repeat task every 15 minutes)
* Actions: Start a program (C:\partos\example-connector\launch.bat)



Usage
-----

The connector can be called in three ways.

In the normal operating mode, it will check for new orders, import any orders found, and quit. This is the mode that is used when scheduling the connector to run at regular intervals via `launch.bat`. In this mode, no command line arguments are needed:

    python connector.py

To import one particular order number, simply provide the integer order number as a single command line argument. For example, to import Order #123:

    python connector.py 123

To simply test your JobBOSS connection, run in test mode:

    python connector.py test

This will print the number of jobs in the database in order to verify database access.
