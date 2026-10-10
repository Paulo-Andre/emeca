from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("historico", "0003_campos_certificado_oficial"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracaoano",
            name="data_conclusao",
            field=models.CharField(blank=True, max_length=30),
        ),
    ]
