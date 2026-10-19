"""Phase08 reduce decrypted saved-credential residency in Android Activity.

The UI retains only server/account metadata. Decrypt the existing Keystore
vault only when the user selects or changes a saved account. Python strings
and JNI can still leave temporary copies in managed memory; this is NOT
guaranteed secure erasure. The on-disk encrypted format is unchanged.
"""


def _identity(record):
    if not isinstance(record, dict):
        raise ValueError("Invalid saved account")
    server, account = record.get("server"), record.get("account")
    if not isinstance(server, str) or not server:
        raise ValueError("Invalid saved server")
    if not isinstance(account, str) or not account:
        raise ValueError("Invalid saved account")
    return (server, account)


def public_accounts(records):
    """Only expose non-secret fields to long-lived UI application state."""
    if not isinstance(records, list):
        raise ValueError("Invalid saved account records")
    return [{"server": _identity(record)[0], "account": _identity(record)[1]}
            for record in records]


def saved_password(vault, server, account):
    """Read a saved secret on explicit selection; do not create a secret cache."""
    for record in vault.load():
        if _identity(record) == (server, account):
            secret = record.get("password")
            if not isinstance(secret, str) or not secret:
                raise ValueError("Invalid saved credential")
            return secret
    raise ValueError("Saved credential not found")


def store_account(vault, server, account, password):
    if not isinstance(password, str) or not password:
        raise ValueError("Invalid credential")
    records = vault.load()
    remaining = [row for row in records if _identity(row) != (server, account)]
    remaining.append({"server": server, "account": account, "password": password})
    vault.save(remaining)
    return public_accounts(remaining)


def delete_account(vault, server, account):
    records = vault.load()
    remaining = [row for row in records if _identity(row) != (server, account)]
    vault.save(remaining)
    return public_accounts(remaining)
