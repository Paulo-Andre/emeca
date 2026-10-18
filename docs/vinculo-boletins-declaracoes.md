# Identidade dos Boletins: Declarações como fonte oficial

## Regra de negócio

- **Matrículas**: registro feito no momento da matrícula; histórico de informações da época. Nunca sobrescrito automaticamente por Declarações.
- **Declarações**: cadastro do aluno atualmente matriculado/enturmado, administrado pela Secretaria.
- **Histórico Escolar**: registro de trajetória e anos letivos, independente dos dois cadastros anteriores.
- **Boletins**: notas/faltas por período com `AlunoBoletim.declaracao` como identificação oficial da criança. O CPF do pai não autoriza acesso público; somente CPF da mãe ou do responsável + nascimento no **mesmo registro de Declarações**.

`AlunoBoletim.nome` conserva o nome vindo da planilha; `nome_oficial` mostra o nome atual da Declaração no site e no PDF. Em edição, só a Secretaria pode vincular uma Declaração a um perfil. Um vínculo já confirmado não é trocado automaticamente por correspondência de nome.

## Migração dos dados históricos

A migração `site_publico.0013_alunoboletim_declaracao` cria um vínculo único e opcional por perfil, com `on_delete=PROTECT`. A única vinculação automática é entre **nomes completos normalizados inequívocos**, sem duplicidade em nenhum dos lados e sem divergência de nascimento quando ambas as datas estão preenchidas. A migração não apaga alunos, notas, boletins ou Declarações.

Perfis que não puderem ser associados permanecem sem vínculo **para revisão administrativa**. Esse período não pode ser publicado até resolver todas as pendências. Um período legado já publicado pode conter vínculos pendentes após a migração: a consulta pública e o envio personalizado WhatsApp não permitem acesso a registros sem vínculo, e a Secretaria precisa conferir o período.

## Fluxo da Secretaria

1. Importar a planilha da turma: período entra em rascunho; notas e faltas são preservadas.
2. Abrir o período e conferir indicadores **Vincular Declaração** / **Acesso pronto**.
3. Para vínculos pendentes, usar **Editar aluno e notas** → selecionar o registro correspondente em Declarações. A lista diferencia nome, turma, data de nascimento e ID; homônimos não são ligados por nome.
4. Se não houver Declaração, corrigir/cadastrar na Secretaria e retornar ao Boletim.
5. Conferir notas e faltas totais (coluna F). Publicar somente quando todos os boletins tiverem vínculo.
6. CPF/nascimento devem ser atualizados em Declarações. O vínculo por ID permanece intacto mesmo se o nome mudar.

**Segurança:** não mesclar notas nem reapontar automaticamente um vínculo confirmado; não recuperar CPF/nascimento de Matrículas antigas; não efetuar alterações destrutivas em massas de dados.

## Pré-implantação e verificações

Faça um backup restaurável do banco EMECA **antes da migração**. Não rode atualizações em paralelo com importações de boletins. Valide os testes automatizados antes de implantar.

```bash
cd /srv/projetos/emeca
git status --short
docker compose exec -T web python manage.py showmigrations site_publico
# Após atualizar o código e efetuar backup consistente:
docker compose exec -T web python manage.py migrate --plan
docker compose exec -T web python manage.py migrate
docker compose exec -T web python manage.py check
docker compose exec -T web python manage.py test site_publico.test_vinculo_declaracao usuarioSec.test_whatsapp
```

Após a migração, confira **somente quantidades** (sem divulgar dados pessoais em logs públicos):

```bash
docker compose exec -T web python manage.py shell -c '
from site_publico.models import BoletimAluno
print("Boletins:", BoletimAluno.objects.count())
print("Sem Declaração:", BoletimAluno.objects.filter(aluno__declaracao__isnull=True).count())
print("Publicados com vínculo pendente:", BoletimAluno.objects.filter(periodo__publicado=True, aluno__declaracao__isnull=True).count())
'
```

Para os registros que permanecerem sem vínculo, usar a interface de revisão; **não** atualizar IDs diretamente no banco sem conferir a criança.
