from django import template

register = template.Library()


@register.filter
def mask_cpf(value):
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) != 11:
        return "***.***.***-**" if digits else ""
    return f"***.***.***-{digits[-2:]}"


@register.filter
def mask_birth(value):
    text = str(value or "").strip()
    if len(text) >= 10 and text[2] in "/-" and text[5] in "/-":
        return f"{text[:2]}/{text[3:5]}/****"
    return "****" if text else ""


@register.filter
def mask_identity(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 3:
        return "*" * len(text)
    return "*" * (len(text) - 3) + text[-3:]
