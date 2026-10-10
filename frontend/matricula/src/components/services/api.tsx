export async function enviarMatricula(dados: any) {
  const response = await fetch("https://emeca.pythonanywhere.com/matricula/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(dados),
    
  });

  if (!response.ok) {
    throw new Error("Erro ao enviar");
  }

  return response.json();
}
