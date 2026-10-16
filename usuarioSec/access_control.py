from django.contrib.auth.models import Group

GRUPO_ADMIN = "EMECA - Administração"
GRUPO_SECRETARIA = "EMECA - Secretaria"
GRUPO_HISTORICO = "EMECA - Histórico"
GRUPO_BOLETINS = "EMECA - Boletins"
GRUPO_SITE = "EMECA - Site"
GRUPO_WHATSAPP = "EMECA - WhatsApp"

GRUPOS_EMECA = {
    "administracao": GRUPO_ADMIN,
    "secretaria": GRUPO_SECRETARIA,
    "historico": GRUPO_HISTORICO,
    "boletins": GRUPO_BOLETINS,
    "site": GRUPO_SITE,
    "whatsapp": GRUPO_WHATSAPP,
}

ROTULOS_PERFIS = [
    ("secretaria", "Secretaria / Matrículas / Declarações"),
    ("historico", "Histórico Escolar"),
    ("boletins", "Boletins"),
    ("site", "Gestão do Site"),
    ("whatsapp", "WhatsApp"),
    ("administracao", "Administração completa"),
]


def nomes_grupos_usuario(user):
    if not getattr(user, "is_authenticated", False):
        return set()
    if user.is_superuser:
        return {GRUPO_ADMIN}
    return set(user.groups.filter(name__in=GRUPOS_EMECA.values()).values_list("name", flat=True))


def usuario_tem_modulo(user, modulo, *, strict=True):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True

    grupos = nomes_grupos_usuario(user)
    if GRUPO_ADMIN in grupos:
        return True

    grupo_esperado = GRUPOS_EMECA.get(modulo)
    if grupo_esperado and grupo_esperado in grupos:
        return True

    # Compatibilidade de transição. Em produção o padrão é strict=True;
    # a migração inclui todos os usuários existentes no grupo Administração.
    if not strict and not grupos:
        return True
    return False


def atribuir_perfis(user, perfis):
    selecionados = set(perfis or [])
    grupos = Group.objects.filter(name__in=GRUPOS_EMECA.values())
    user.groups.remove(*grupos)

    if "administracao" in selecionados:
        grupo = Group.objects.get(name=GRUPO_ADMIN)
        user.groups.add(grupo)
        return

    nomes = [
        GRUPOS_EMECA[chave]
        for chave in selecionados
        if chave in GRUPOS_EMECA and chave != "administracao"
    ]
    if nomes:
        user.groups.add(*Group.objects.filter(name__in=nomes))
