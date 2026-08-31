# Prerequisites of the components

Most components have prerequisites - installed software, configuration in place, keys or information available.
Some of these prerequisites are common to multiple components. To avoid duplicating the instructions the prerequisites
are compiled here. Do not install or configure the below unless you need it.

## Microsoft SQL Server

Download page: https://www.microsoft.com/en-us/sql-server/sql-server-downloads
Edition: SQL Server 2025 Developer, Standard Developer Edition

- Server Name: your localhost. You can open command prompt and execute `hostname` to get it
- Authentication: `Windows Authentication` (this is the default)
- User Name: the local user name. You can use command `whoami` to get it
- Password: this will likely be blank
- Database Name: none yet, see below

### SQL Server Management Studio

Download page: https://learn.microsoft.com/en-us/ssms/install/install

Once you start SSMS you will be asked to Connect. There are two tabs at the top - History and Browse. Click on Browse, open the fold for Local and you should see your local server. Once you select it you may get an error about certificate on path being issued by someone not trusted. The easiest fix, since we are connecting to localhost, is to tick the checkbox `Trust Server Certificate` in the lower part. In real environment you would likely want to configure the certificates instead.

### Database for the application

Use SSMS to create new database:
- Database name: `els_db`
- Owner: `<default>`
- Go to the server properties, `Security` and allow `SQL Server and Windows Authentication mode`
- It might be a good idea to set the database collation in `Options` to `Latin1_General_100_CI_AS_SC_UTF8`

### Account admin user for the database

Use SSMS to create new Security / Login:
- Login name: `els_accountadmin`
- Select `SQL Authentication`
- Pick a strong password and tick off `Enforce password expiration`
- Change default database to `els_db`
- Go to `User Mapping` and map the login to database `els_db`
- In the bottom part select appropriate roles: `db_datareader`, `db_datawriter`, `db_ddladmin` and `db_owner`

### Enable connecting to the server

By detault the service `SQL Server Browser` is set to disabled and so is the `TCP/IP` protocol. In order to able to connect using JDBC you may have to:
- Go to `C:\Windows\SysWOW64`
- Run `SQLServerManager17.msc`
- Navigate to `SQL Server Network Configuration` / `Protocols for <your instance name>`
- In the right panel make sure `TCP/IP` is enabled. Also go into `Properties`, table `IP Addresses` and note down the `TCP Port` number
- Go to `SQL Server Services` and restart the SQL Server service

## Flyway CLI

Download page: https://www.red-gate.com/products/flyway/community/download/

This downloads `Flyway_Desktop.exe`. It contains both the GUI and CLI versions. Once installed with the default settings
the CLI would be here:
- `C:\Program Files\Red Gate\Flyway Desktop\flyway`

## dbt

Installation:
```
pip install dbt-core dbt-sqlserver
```

The `dbt init` wizard is not able to correctly setup `profiles.yml` for SQL Server. It will be missing entries. It may be easier to create
the file manually in advance.

Path: `~/.dbt/profiles.yml`
Content:
```yml
els_transform:
  outputs:
    dev:
      driver: "ODBC Driver 18 for SQL Server"
      database: els_db
      schema: dw
      host: <<host name>>
      trust_cert: true
      user: <<database user>>
      password: <<password>>
      port: 1433
      threads: 1
      type: sqlserver
  target: dev
```
