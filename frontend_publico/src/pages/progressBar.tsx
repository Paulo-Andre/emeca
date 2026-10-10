type Props = {
  etapaAtual: number;
};

const etapas = [
  "Aluno",
  "Pai",
  "Mãe",
  "Responsável",
  "Estado Civil",
  "Endereço",
  "Histórico",
  "Fim",
];

export default function ProgressBar({ etapaAtual }: Props) {
  return (
    <div style={{ marginTop: "15px" }}>
      
      {/* BARRA */}
      <div style={{
        display: "flex",
        gap: "6px"
      }}>
        {etapas.map((_, index) => (
          <div
            key={index}
            style={{
              flex: 1,
              height: "6px",
              borderRadius: "4px",
              background:
                index <= etapaAtual ? "#59d400" : "#64748b",
              transition: "0.3s"
            }}
          />
        ))}
      </div>

      {/* TEXTO */}
      <span style={{
        display: "block",
        marginTop: "8px",
        fontSize: "12px",
        color: "#e5e7eb"
      }}>
        Etapa {etapaAtual + 1} de {etapas.length} — {etapas[etapaAtual]}
      </span>

    </div>
  );
}