from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("usuarioSec", "0018_sessao_whatsapp_limpeza_pendente"),
    ]

    operations = [
        migrations.AlterField(
            model_name="envioboletimwhatsapp",
            name="modo",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("todos", "Todos"),
                    ("turma", "Por turma"),
                    ("turma_boletim", "Turma cadastrada em Boletins"),
                    ("individual", "Individual"),
                ],
            ),
        ),
    ]
