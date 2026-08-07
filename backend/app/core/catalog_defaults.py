"""Catálogo padrão de plataformas e modalidades de golpe do Squad Digital.

Módulo de dados puros, sem dependência de ORM ou de sessão: é importado tanto
pela migration que semeia os tenants existentes quanto por
app/services/catalog_service.py, que reconcilia as entradas de sistema a cada
leitura do catálogo. Manter uma fonte só evita que as duas listas divirjam.

Acrescentar uma entrada aqui a propaga para todos os escritórios na próxima
leitura do catálogo (a reconciliação é por slug, com ON CONFLICT DO NOTHING).
**Nunca renomeie um slug já publicado** — ele é a identidade da entrada; o
`label` é que pode mudar, inclusive pelo próprio escritório.
"""

from typing import NamedTuple

from app.models.enums import FraudType


class PlatformDefault(NamedTuple):
    """Entrada padrão do catálogo de plataformas."""

    slug: str
    label: str
    sort_order: int


class FraudModalityDefault(NamedTuple):
    """Entrada padrão do catálogo de modalidades, com a família a que pertence."""

    slug: str
    label: str
    family: FraudType
    sort_order: int


#: Plataformas onde as fraudes do Squad Digital acontecem (ver
#: prompts/digital/evidence/specialist.md, que carrega conhecimento técnico
#: específico de várias delas).
DEFAULT_PLATFORMS: tuple[PlatformDefault, ...] = (
    PlatformDefault("whatsapp", "WhatsApp", 10),
    PlatformDefault("meta_facebook", "Facebook (Meta)", 20),
    PlatformDefault("facebook_marketplace", "Marketplace do Facebook", 30),
    PlatformDefault("instagram", "Instagram (Meta)", 40),
    PlatformDefault("mercado_livre", "Mercado Livre", 50),
    PlatformDefault("shopee", "Shopee", 60),
    PlatformDefault("olx", "OLX", 70),
    PlatformDefault("amazon", "Amazon", 80),
    PlatformDefault("aliexpress", "AliExpress", 90),
    PlatformDefault("tiktok", "TikTok", 100),
    PlatformDefault("telegram", "Telegram", 110),
    PlatformDefault("instituicao_financeira", "Instituição financeira / PIX", 120),
    PlatformDefault("site_falso", "Site falso / e-commerce fraudulento", 130),
    PlatformDefault("outra_plataforma", "Outra plataforma", 999),
)

#: Modalidades de golpe conhecidas, cada uma ancorada em uma família de
#: FraudType — é a família que o grafo e os prompts leem.
DEFAULT_FRAUD_MODALITIES: tuple[FraudModalityDefault, ...] = (
    FraudModalityDefault("pix", "Golpe do PIX", FraudType.PIX, 10),
    FraudModalityDefault("falsa_central", "Falsa central de atendimento", FraudType.PIX, 20),
    FraudModalityDefault(
        "pix_devolucao", "Falso PIX por engano / pedido de devolução", FraudType.PIX, 30
    ),
    FraudModalityDefault(
        "marketplace", "Compra não entregue em marketplace", FraudType.MARKETPLACE, 40
    ),
    FraudModalityDefault(
        "anuncio_fraudulento",
        "Anúncio fraudulento em marketplace",
        FraudType.MARKETPLACE,
        50,
    ),
    FraudModalityDefault(
        "pagamento_fora_plataforma",
        "Pagamento induzido fora da plataforma",
        FraudType.MARKETPLACE,
        60,
    ),
    FraudModalityDefault("fake_profile", "Perfil falso em rede social", FraudType.FAKE_PROFILE, 70),
    FraudModalityDefault("clonagem_whatsapp", "Clonagem de WhatsApp", FraudType.FAKE_PROFILE, 80),
    FraudModalityDefault(
        "loja_falsa_rede_social",
        "Loja falsa em rede social",
        FraudType.FAKE_PROFILE,
        90,
    ),
    FraudModalityDefault("fake_lawyer", "Falso advogado", FraudType.FAKE_LAWYER, 100),
    FraudModalityDefault(
        "falso_preposto", "Falso preposto de escritório", FraudType.FAKE_LAWYER, 110
    ),
    FraudModalityDefault("other", "Outra modalidade", FraudType.OTHER, 999),
)
