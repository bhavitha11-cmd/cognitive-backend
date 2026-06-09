import contextvars

ip_address_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "ip_address", default=None
)
user_agent_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "user_agent", default=None
)


def set_audit_context(ip_address: str | None, user_agent: str | None) -> None:
    ip_address_var.set(ip_address)
    user_agent_var.set(user_agent)


def get_audit_context() -> tuple[str | None, str | None]:
    return ip_address_var.get(), user_agent_var.get()
