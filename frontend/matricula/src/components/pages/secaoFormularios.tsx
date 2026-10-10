interface Dados {
  texto: string;
}
export default function SecaoFormulario({ texto }: Dados) {
  return (
    <>
      <div className="secao">
        <h2>{texto}</h2>
      </div>
    </>
  );
}
