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
  const progresso = Math.round(((etapaAtual + 1) / etapas.length) * 100);

  return (
    <div className="progress-wrap" aria-label="Progresso do preenchimento">
      <div className="progress-summary">
        <span className="progress-label">
          Etapa {etapaAtual + 1} de {etapas.length}
        </span>
        <strong>{etapas[etapaAtual]}</strong>
        <span className="progress-percent">{progresso}%</span>
      </div>

      <div className="progress-bar" aria-hidden="true">
        {etapas.map((etapa, index) => (
          <div
            key={etapa}
            className={[
              "progress-step",
              index < etapaAtual ? "is-complete" : "",
              index === etapaAtual ? "is-current" : "",
            ].filter(Boolean).join(" ")}
          />
        ))}
      </div>

      <div className="progress-steps" aria-hidden="true">
        {etapas.map((etapa, index) => (
          <span
            key={etapa}
            className={index === etapaAtual ? "is-current" : index < etapaAtual ? "is-complete" : ""}
          >
            {index + 1}
          </span>
        ))}
      </div>
    </div>
  );
}
