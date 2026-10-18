# Boletins: coluna H e símbolo oficial no PDF

## Regra de faltas confirmada pela Secretaria

No layout `Notas e Faltas` usado pela escola, **a coluna H é a primeira coluna de faltas e contém o total do aluno no período**. As demais colunas de faltas são decomposições ou detalhamentos da primeira, portanto **não devem ser somadas, nem usadas como substitutas do total**.

O importador `site_publico/boletim_importacao.py` utiliza o índice 7 (coluna H) como `faltas_totais`. Se o arquivo antigo possuir menos de oito colunas, as notas são preservadas e o total fica vazio para revisão manual, sem inferência.

O importador armazena `BoletimAluno.faltas_totais` e mantém `NotaBoletim.faltas` em branco. O PDF, o site público e o envio por WhatsApp usam o mesmo total do Boletim.

## Símbolo institucional

O gerador comum `gerar_pdf_boletim` agora carrega primeiro `ConfiguracaoSite.logo_site` (imagem definida pelo administrador do site). Se estiver vazio ou ilegível, carrega o arquivo estático `imagens/logo2.png.png` distribuído com o EMECA. O símbolo é redimensionado com proporção preservada, limitado ao espaço de 22 mm no cabeçalho. O conteúdo é convertido em memória para PNG de no máximo 600 px na maior dimensão, economizando no envio de muitos PDFs.

O site público e o worker do WhatsApp chamam este mesmo gerador. PDFs **já enviados anteriormente** não são alterados retroativamente.

## Conferir boletins já importados

**Não reimporte simplesmente uma planilha para consertar faltas:** a rotina de importação substitui os boletins do período, incluindo notas, e pode gerar efeitos indesejados.

A correção dedicada está disponível no comando `conferir_faltas_boletim`. Ela compara somente as faltas totais da coluna H com um **período exato**. O comando não altera notas, alunos, declarações, matrículas ou histórico; não faz correspondência automática ambígua entre homônimos.

1. Faça e confira um **backup restaurável do banco EMECA**.
2. Confirme o ID do período no painel de Boletins.
3. Disponibilize o XLS original no container web de modo seguro.
4. Rode a prévia (sem escrita):

```bash
docker compose exec -T web python manage.py conferir_faltas_boletim \
  /tmp/notas-original.xls --periodo-id 123
```

5. Corrija manualmente qualquer problema indicado na prévia. Somente quando **nenhum aluno** estiver pendente, use:

```bash
docker compose exec -T web python manage.py conferir_faltas_boletim \
  /tmp/notas-original.xls --periodo-id 123 --aplicar --backup-confirmado
```

O valor `123` é **apenas exemplo**, não um ID real. O comando exige correspondência de organização, ano, período e turma, e verifica nome e número de chamada quando disponível. Não compartilhe planilhas com dados de crianças em logs ou canais públicos.

Após a correção, abra o período e verifique as faltas totais de alguns alunos diretamente contra a coluna H. Faça o download de um PDF para confirmar a imagem da escola e o valor exibido.

**Atenção:** períodos publicados ou PDFs já enviados podem refletir dados anteriores. Um PDF baixado após a alteração exibirá o valor novo; documentos já entregues exigem decisão administrativa sobre reemissão e eventual comunicação aos responsáveis.
