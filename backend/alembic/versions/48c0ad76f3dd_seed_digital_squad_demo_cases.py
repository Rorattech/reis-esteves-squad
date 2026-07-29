"""seed digital squad demo cases

Revision ID: 48c0ad76f3dd
Revises: 41280d8b096c
Create Date: 2026-07-29 13:58:00.032007

Popula o tenant de dev (d27cf82e3178) com casos fictícios cobrindo os
cenários principais do Squad Digital (Marketplace, PIX, WhatsApp clonado,
Shopee, falso advogado) — dados suficientes para desenvolver/testar intake,
roteamento, lista de casos e formulário sem depender de nenhum dado real.

Guardas de segurança (mesmo padrão de d27cf82e3178):
- Só roda se BACKEND_ENV=development.
- Idempotente: cada cliente/caso usa um UUID determinístico (uuid5 a partir
  de um label fixo) + ON CONFLICT (id) DO NOTHING — seguro rodar
  `alembic upgrade head` de novo num banco que já tem esses dados.
- Usa app.current_tenant (não app.bootstrap): ao contrário de tenants/users,
  clients/cases/case_intakes/case_documents não têm policy auth_bootstrap
  (ver migration 3abdfd696724, _BOOTSTRAP_TABLES) — a policy tenant_isolation
  exige app.current_tenant apontando para o tenant de dev.
"""

import json
import uuid
from datetime import date
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from app.core.config import settings

# revision identifiers, used by Alembic.
revision: str = "48c0ad76f3dd"
down_revision: Union[str, Sequence[str], None] = "41280d8b096c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TENANT_SLUG = "reis-esteves"
_ADMIN_EMAIL = "admin@reisesteves.com.br"
_SEED_NAMESPACE = uuid.UUID("6f6f6f6f-6f6f-6f6f-6f6f-6f6f6f6f6f6f")

# label é a chave estável usada para derivar o UUID determinístico de cada
# entidade (uuid5) — nunca é exibido ao usuário, só garante idempotência.
_DEMO_CASES = [
    {
        "label": "demo-case-marketplace-mercado-livre",
        "client_name": "Fernanda Albuquerque Lima",
        "platform": "Mercado Livre",
        "fraud_type": "marketplace",
        "urgency": "medium",
        "matter": "produto não entregue após pagamento via Mercado Pago",
        "narrative": (
            "Cliente comprou um notebook usado por R$ 2.800,00 num anúncio do Mercado Livre. "
            "O vendedor pediu para finalizar a compra fora da plataforma, via PIX direto, "
            "alegando problema no Mercado Pago. Após o pagamento, o vendedor sumiu e o anúncio "
            "foi removido."
        ),
        "estimated_loss_amount": "2800.00",
        "incident_date": date(2026, 6, 12),
        "has_police_report": False,
        "claimed_documents": ["print_conversa_vendedor.png", "comprovante_pix.png"],
        "pending_information": ["boletim_de_ocorrencia", "print_do_anuncio_original"],
        "checklist": [
            ("Print da conversa com o vendedor", "received"),
            ("Comprovante de pagamento PIX", "received"),
            ("Boletim de Ocorrência", "pending"),
            ("Print do anúncio original", "pending"),
        ],
    },
    {
        "label": "demo-case-pix-golpe-whatsapp",
        "client_name": "Carlos Eduardo Nascimento",
        "platform": "PIX",
        "fraud_type": "pix",
        "urgency": "high",
        "matter": "golpe do PIX via contato de WhatsApp desconhecido",
        "narrative": (
            "Cliente recebeu mensagem no WhatsApp de um número desconhecido se passando por "
            "um familiar pedindo PIX urgente de R$ 1.500,00 para uma emergência médica. O "
            "cliente transferiu o valor antes de perceber o golpe. O ocorrido foi há 2 dias."
        ),
        "estimated_loss_amount": "1500.00",
        "incident_date": date(2026, 7, 27),
        "has_police_report": False,
        "claimed_documents": ["comprovante_pix.png", "print_conversa_whatsapp.png"],
        "pending_information": ["boletim_de_ocorrencia", "dados_da_conta_destino"],
        "checklist": [
            ("Comprovante de transferência PIX", "received"),
            ("Print da conversa no WhatsApp", "received"),
            ("Boletim de Ocorrência", "pending"),
            ("Dados da conta bancária de destino", "pending"),
        ],
    },
    {
        "label": "demo-case-whatsapp-clonado",
        "client_name": "Beatriz Souza Ramalho",
        "platform": "WhatsApp",
        "fraud_type": "fake_profile",
        "urgency": "critical",
        "matter": "clonagem de WhatsApp com pedido de dinheiro aos contatos",
        "narrative": (
            "O WhatsApp da cliente foi clonado após ela receber e repassar, por engano, um "
            "código de verificação recebido por SMS. O golpista está pedindo dinheiro para "
            "todos os contatos da cliente, se passando por ela. A conta ainda está sob controle "
            "do golpista."
        ),
        "estimated_loss_amount": None,
        "incident_date": date(2026, 7, 28),
        "has_police_report": False,
        "claimed_documents": ["print_tela_login_suspeito.png"],
        "pending_information": [
            "boletim_de_ocorrencia",
            "lista_de_contatos_avisados",
            "confirmacao_de_recuperacao_da_conta",
        ],
        "checklist": [
            ("Print da tela de login suspeito", "received"),
            ("Boletim de Ocorrência", "pending"),
            ("Lista de contatos que receberam a mensagem falsa", "pending"),
        ],
    },
    {
        "label": "demo-case-shopee-produto-nao-entregue",
        "client_name": "Rodrigo Matias Pereira",
        "platform": "Shopee",
        "fraud_type": "marketplace",
        "urgency": "low",
        "matter": "produto não entregue e vendedor sem resposta",
        "narrative": (
            "Cliente comprou um smartphone na Shopee há 45 dias. O rastreamento mostra que o "
            "pacote foi entregue, mas o cliente nunca recebeu nada — o endereço de entrega "
            "registrado na plataforma está incorreto. A Shopee negou o reembolso."
        ),
        "estimated_loss_amount": "950.00",
        "incident_date": date(2026, 6, 1),
        "has_police_report": False,
        "claimed_documents": ["print_pedido_shopee.png", "print_negativa_reembolso.png"],
        "pending_information": ["comprovante_de_endereco"],
        "checklist": [
            ("Print do pedido na Shopee", "received"),
            ("Print da negativa de reembolso", "received"),
            ("Comprovante de endereço", "pending"),
        ],
    },
    {
        "label": "demo-case-falso-advogado",
        "client_name": "Marta Cristina Oliveira",
        "platform": "WhatsApp",
        "fraud_type": "fake_lawyer",
        "urgency": "high",
        "matter": "falso advogado cobrando honorários para liberar suposta indenização",
        "narrative": (
            "Cliente foi contatada por alguém se identificando como advogado de um grande "
            "escritório, alegando que ela tinha direito a uma indenização de um processo "
            "coletivo. Para 'liberar' o valor, pediram o pagamento de R$ 3.200,00 em taxas "
            "cartorárias via PIX. Depois do pagamento, o suposto advogado parou de responder."
        ),
        "estimated_loss_amount": "3200.00",
        "incident_date": date(2026, 7, 10),
        "has_police_report": True,
        "claimed_documents": [
            "comprovante_pix.png",
            "print_conversa_whatsapp.png",
            "boletim_de_ocorrencia.pdf",
        ],
        "pending_information": ["numero_oab_informado_pelo_golpista"],
        "checklist": [
            ("Comprovante de pagamento PIX", "received"),
            ("Print da conversa no WhatsApp", "received"),
            ("Boletim de Ocorrência", "received"),
            ("Número de OAB informado pelo golpista", "pending"),
        ],
    },
    {
        "label": "demo-case-marketplace-facebook-perfil-falso",
        "client_name": "Juliana Gomes Barreto",
        "platform": "Facebook Marketplace",
        "fraud_type": "fake_profile",
        "urgency": "medium",
        "matter": "perfil falso vendendo móveis no Facebook Marketplace",
        "narrative": (
            "Cliente negociou a compra de um sofá por R$ 1.100,00 com um perfil do Facebook "
            "Marketplace criado há poucos dias. Pagou metade do valor como sinal via PIX para "
            "reservar o produto. O perfil foi excluído logo em seguida e o produto nunca foi "
            "entregue."
        ),
        "estimated_loss_amount": "550.00",
        "incident_date": date(2026, 6, 20),
        "has_police_report": False,
        "claimed_documents": ["print_anuncio_facebook.png", "comprovante_pix.png"],
        "pending_information": ["boletim_de_ocorrencia"],
        "checklist": [
            ("Print do anúncio no Facebook Marketplace", "received"),
            ("Comprovante de pagamento PIX (sinal)", "received"),
            ("Boletim de Ocorrência", "pending"),
        ],
    },
    {
        "label": "demo-case-pix-falso-funcionario-banco",
        "client_name": "Antonio Carlos Ferreira",
        "platform": "PIX",
        "fraud_type": "pix",
        "urgency": "high",
        "matter": "golpe do falso funcionário de banco por telefone",
        "narrative": (
            "Cliente recebeu ligação de uma pessoa se identificando como funcionário do banco, "
            "alertando sobre uma 'transação suspeita' e pedindo que ele confirmasse dados e "
            "fizesse uma transferência PIX para uma 'conta de segurança'. O cliente transferiu "
            "R$ 4.700,00 antes de perceber que não era realmente o banco."
        ),
        "estimated_loss_amount": "4700.00",
        "incident_date": date(2026, 7, 25),
        "has_police_report": True,
        "claimed_documents": ["comprovante_pix.png", "boletim_de_ocorrencia.pdf"],
        "pending_information": ["gravacao_da_ligacao_se_houver", "extrato_bancario_do_periodo"],
        "checklist": [
            ("Comprovante de transferência PIX", "received"),
            ("Boletim de Ocorrência", "received"),
            ("Extrato bancário do período", "pending"),
        ],
    },
]


def _seed_id(label: str) -> str:
    return str(uuid.uuid5(_SEED_NAMESPACE, label))


def upgrade() -> None:
    """Upgrade schema."""
    if settings.backend_env != "development":
        return

    bind = op.get_bind()
    bind.execute(sa.text("SELECT set_config('app.bootstrap', 'true', false)"))

    tenant_id = bind.execute(
        sa.text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": _TENANT_SLUG}
    ).scalar_one_or_none()
    admin_user_id = bind.execute(
        sa.text("SELECT id FROM users WHERE tenant_id = :tenant_id AND email = :email"),
        {"tenant_id": tenant_id, "email": _ADMIN_EMAIL},
    ).scalar_one_or_none()

    if tenant_id is None or admin_user_id is None:
        # Tenant/admin de dev (d27cf82e3178) não existem — nada a semear
        # (ex.: BACKEND_ENV=development mas banco criado antes daquela seed).
        return

    bind.execute(sa.text("SELECT set_config('app.bootstrap', 'false', false)"))
    bind.execute(
        sa.text("SELECT set_config('app.current_tenant', :tenant_id, false)"),
        {"tenant_id": str(tenant_id)},
    )

    for demo in _DEMO_CASES:
        client_id = _seed_id(f"{demo['label']}-client")
        case_id = _seed_id(f"{demo['label']}-case")

        bind.execute(
            sa.text(
                "INSERT INTO clients (id, tenant_id, full_name) "
                "VALUES (:id, :tenant_id, :full_name) ON CONFLICT (id) DO NOTHING"
            ),
            {"id": client_id, "tenant_id": str(tenant_id), "full_name": demo["client_name"]},
        )

        bind.execute(
            sa.text(
                "INSERT INTO cases "
                "(id, tenant_id, user_id, client_id, area, matter, platform, fraud_type, "
                " urgency, status, current_module, human_review_required) "
                "VALUES (:id, :tenant_id, :user_id, :client_id, 'digital', :matter, :platform, "
                " :fraud_type, :urgency, 'in_progress', 'intake', true) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": case_id,
                "tenant_id": str(tenant_id),
                "user_id": str(admin_user_id),
                "client_id": client_id,
                "matter": demo["matter"],
                "platform": demo["platform"],
                "fraud_type": demo["fraud_type"],
                "urgency": demo["urgency"],
            },
        )

        bind.execute(
            sa.text(
                "INSERT INTO case_intakes "
                "(id, tenant_id, case_id, submitted_by, narrative, estimated_loss_amount, "
                " incident_date, has_police_report, claimed_documents, pending_information) "
                "VALUES (:id, :tenant_id, :case_id, :submitted_by, :narrative, "
                " :estimated_loss_amount, :incident_date, :has_police_report, "
                " CAST(:claimed_documents AS jsonb), CAST(:pending_information AS jsonb)) "
                "ON CONFLICT (case_id) DO NOTHING"
            ),
            {
                "id": _seed_id(f"{demo['label']}-intake"),
                "tenant_id": str(tenant_id),
                "case_id": case_id,
                "submitted_by": str(admin_user_id),
                "narrative": demo["narrative"],
                "estimated_loss_amount": demo["estimated_loss_amount"],
                "incident_date": demo["incident_date"],
                "has_police_report": demo["has_police_report"],
                "claimed_documents": json.dumps(demo["claimed_documents"]),
                "pending_information": json.dumps(demo["pending_information"]),
            },
        )

        for name, status in demo["checklist"]:
            bind.execute(
                sa.text(
                    "INSERT INTO case_documents (id, tenant_id, case_id, name, status, origin) "
                    "VALUES (:id, :tenant_id, :case_id, :name, :status, 'intake') "
                    "ON CONFLICT (case_id, name) DO NOTHING"
                ),
                {
                    "id": _seed_id(f"{demo['label']}-doc-{name}"),
                    "tenant_id": str(tenant_id),
                    "case_id": case_id,
                    "name": name,
                    "status": status,
                },
            )


def downgrade() -> None:
    """Downgrade schema."""
    if settings.backend_env != "development":
        return

    bind = op.get_bind()
    bind.execute(sa.text("SELECT set_config('app.bootstrap', 'true', false)"))

    tenant_id = bind.execute(
        sa.text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": _TENANT_SLUG}
    ).scalar_one_or_none()
    if tenant_id is None:
        return

    bind.execute(sa.text("SELECT set_config('app.bootstrap', 'false', false)"))
    bind.execute(
        sa.text("SELECT set_config('app.current_tenant', :tenant_id, false)"),
        {"tenant_id": str(tenant_id)},
    )

    case_ids = [_seed_id(f"{demo['label']}-case") for demo in _DEMO_CASES]
    client_ids = [_seed_id(f"{demo['label']}-client") for demo in _DEMO_CASES]

    bind.execute(sa.text("DELETE FROM cases WHERE id = ANY(:ids)"), {"ids": case_ids})
    bind.execute(sa.text("DELETE FROM clients WHERE id = ANY(:ids)"), {"ids": client_ids})
