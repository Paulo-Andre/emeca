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
    <div className="progress-wrap" aria-label="Progresso do preenchimento">
      <div className="progress-bar" aria-hidden="true">
        {etapas.map((_, index) => (
          <div
            key={index}
            className={`progress-step ${index <= etapaAtual ? "active" : ""}`}
          />
        ))}
      </div>

      <span className="progress-label">
        Etapa {etapaAtual + 1} de {etapas.length} — {etapas[etapaAtual]}
      </span>
    </div>
  );
}
