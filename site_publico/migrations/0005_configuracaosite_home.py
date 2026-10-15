from django.db import migrations, models


def preencher_home(apps, schema_editor):
    ConfiguracaoSite = apps.get_model("site_publico", "ConfiguracaoSite")
    for config in ConfiguracaoSite.objects.all():
        if not config.home_texto:
            config.home_texto = (
                "A escola é um espaço de aprendizagem, convivência e desenvolvimento. "
                "Nosso objetivo é aproximar estudantes, famílias e comunidade em torno de "
                "uma educação pública acolhedora, responsável e participativa."
            )
        if not config.home_pilar1_texto:
            config.home_pilar1_texto = (
                "Experiências que incentivam leitura, raciocínio, criatividade, autonomia "
                "e participação ativa dos estudantes."
            )
        if not config.home_pilar2_texto:
            config.home_pilar2_texto = (
                "Respeito, cooperação e diálogo fazem parte da construção de um ambiente "
                "escolar acolhedor e responsável."
            )
        if not config.home_pilar3_texto:
            config.home_pilar3_texto = (
                "A participação das famílias fortalece o acompanhamento escolar e aproxima "
                "a escola da comunidade."
            )
        config.save()


class Migration(migrations.Migration):
    dependencies = [("site_publico", "0004_paginapublica")]

    operations = [
        migrations.AddField(model_name="configuracaosite", name="home_titulo", field=models.CharField(blank=True, default="Um espaço para aprender, conviver e crescer", max_length=220)),
        migrations.AddField(model_name="configuracaosite", name="home_texto", field=models.TextField(blank=True)),
        migrations.AddField(model_name="configuracaosite", name="home_pilar1_titulo", field=models.CharField(blank=True, default="Aprendizagem", max_length=120)),
        migrations.AddField(model_name="configuracaosite", name="home_pilar1_texto", field=models.TextField(blank=True)),
        migrations.AddField(model_name="configuracaosite", name="home_pilar2_titulo", field=models.CharField(blank=True, default="Convivência", max_length=120)),
        migrations.AddField(model_name="configuracaosite", name="home_pilar2_texto", field=models.TextField(blank=True)),
        migrations.AddField(model_name="configuracaosite", name="home_pilar3_titulo", field=models.CharField(blank=True, default="Família e comunidade", max_length=120)),
        migrations.AddField(model_name="configuracaosite", name="home_pilar3_texto", field=models.TextField(blank=True)),
        migrations.RunPython(preencher_home, migrations.RunPython.noop),
    ]
