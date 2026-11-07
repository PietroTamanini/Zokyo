"""Provisiona um usuário MariaDB apenas com DML para app/scheduler em produção."""
import os
import re

import pymysql


_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def provision_runtime_user(*, host, database, owner_user, root_password,
                           runtime_user, runtime_password, port=3306):
    if not _IDENTIFIER.fullmatch(database):
        raise ValueError("MYSQL_DATABASE deve conter apenas letras, números e sublinhado.")
    if not _IDENTIFIER.fullmatch(runtime_user):
        raise ValueError("APP_DB_USER deve conter apenas letras, números e sublinhado.")
    if runtime_user.lower() in {"root", owner_user.lower()}:
        raise ValueError("APP_DB_USER deve ser diferente do usuário de migração/root.")
    if not root_password or len(runtime_password) < 24:
        raise ValueError("Configure MYSQL_ROOT_PASSWORD e APP_DB_PASSWORD com pelo menos 24 caracteres.")
    connection = pymysql.connect(
        host=host, port=int(port), user="root", password=root_password,
        autocommit=True, charset="utf8mb4",
    )
    try:
        with connection.cursor() as cursor:
            account = (runtime_user, "%")
            cursor.execute("CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s", (*account, runtime_password))
            cursor.execute("ALTER USER %s@%s IDENTIFIED BY %s", (*account, runtime_password))
            cursor.execute("REVOKE ALL PRIVILEGES, GRANT OPTION FROM %s@%s", account)
            cursor.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{database}`.* TO %s@%s", account,
            )
            cursor.execute("SHOW GRANTS FOR %s@%s", account)
            grants = [str(row[0]).upper() for row in cursor.fetchall()]
        for grant in grants:
            if grant.startswith("GRANT USAGE ON *.* TO "):
                continue
            match = re.match(rf"^GRANT ([A-Z, ]+) ON `{database.upper()}`\.\* TO ", grant)
            if not match or set(match.group(1).split(", ")) != {"SELECT", "INSERT", "UPDATE", "DELETE"}:
                raise RuntimeError("O usuário de execução possui concessões além das operações de dados permitidas.")
    finally:
        connection.close()
    return {"database": database, "runtime_user": runtime_user, "privileges": "SELECT, INSERT, UPDATE, DELETE"}


def main():
    result = provision_runtime_user(
        host=os.environ.get("MYSQL_HOST", "db"),
        port=os.environ.get("MYSQL_PORT", "3306"),
        database=os.environ.get("MYSQL_DATABASE", ""),
        owner_user=os.environ.get("MYSQL_USER", ""),
        root_password=os.environ.get("MYSQL_ROOT_PASSWORD", ""),
        runtime_user=os.environ.get("APP_DB_USER", ""),
        runtime_password=os.environ.get("APP_DB_PASSWORD", ""),
    )
    print(f"Usuário de execução preparado em {result['database']}: {result['runtime_user']} ({result['privileges']}).")


if __name__ == "__main__":
    main()
