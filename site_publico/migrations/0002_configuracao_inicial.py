from django.db import migrations


def criar_configuracao(apps, schema_editor):
    ConfiguracaoSite = apps.get_model("site_publico", "ConfiguracaoSite")
    ConfiguracaoSite.objects.get_or_create(
        pk=1,
        defaults={
            "nome_escola": "E. M. Egídio Cordeiro Aquino",
            "subtitulo": "Educação, acolhimento e aprendizagem construídos juntos.",
            "cidade": "Montes Claros/MG",
        },
    )


def remover_configuracao(apps, schema_editor):
    ConfiguracaoSite = apps.get_model("site_publico", "ConfiguracaoSite")
    ConfiguracaoSite.objects.filter(pk=1).delete()


class Migration(migrations.Migration):
    dependencies = [("site_publico", "0001_initial")]

    operations = [
        migrations.RunPython(criar_configuracao, remover_configuracao),
    ]
