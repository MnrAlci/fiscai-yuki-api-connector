# Security policy

## Reporting a vulnerability
Please do **not** open a public issue for security problems. Use GitHub's private vulnerability reporting ("Security" tab, "Report a vulnerability") on this repository.

Include what you found, how to reproduce it with synthetic data, and the version. Never send real Yuki keys or client data.

## Scope
Of particular interest: any way to write to Yuki without `YUKI_WRITE_ENABLED=ja`, to reuse or bypass a booking token, to leak a key into logs or tool output, or to book a workflow document as a journal entry.

## Handling secrets
If you ever pasted a Yuki key somewhere by mistake, revoke it in Yuki and create a new one.
