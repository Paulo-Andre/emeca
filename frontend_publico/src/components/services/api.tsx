export async function enviarMatricula(dados: any) {
  const response = await fetch("/matricula/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "same-origin",
    body: JSON.stringify(dados),
  });

  if (!response.ok) {
    const detalhe = await response.json().catch(() => null);
    throw new Error(detalhe?.mensagem || "Erro ao enviar matrícula");
  }

  return response.json();
}
