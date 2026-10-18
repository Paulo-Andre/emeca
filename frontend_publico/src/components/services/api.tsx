function getCookie(name: string): string {
  const prefix = name + "=";
  const item = document.cookie
    .split("; ")
    .find((value) => value.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : "";
}

export async function enviarMatricula(dados: import('../useState_SalvandoDados/salvandoDadosUseState').SetDados) {
  const csrfToken = getCookie("csrftoken");
  const response = await fetch("/matricula/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
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
