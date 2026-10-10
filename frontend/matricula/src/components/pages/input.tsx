interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}
interface DadosSelect {
  placeholder: string;
  nomeResposta: string;
  nomeResposta2: string;
  placeholder2: string;
}
import "../css/input.css";
import { useState } from "react";
function Inputf({ required = false, placeholder, ...rest }: InputProps) {
  return (
    <>
      <div className="campo">
        <input {...rest} required={required} />
        <label>{placeholder}</label>
      </div>
    </>
  );
}

function Select({
  placeholder,
  nomeResposta,
  nomeResposta2,
  placeholder2,
  onChange,
}: DadosSelect & {
  onChange: (
    e: React.ChangeEvent<HTMLSelectElement | HTMLInputElement>
  ) => void;
}) {
  const [valorSelect, setValorSelect] = useState("");

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setValorSelect(e.target.value);
    onChange(e);
  }

  return (
    <div className="campo">
      <select
        name={nomeResposta}
        value={valorSelect}
        required
        onChange={handleChange}
      >
        <option value="" disabled hidden />
        <option value="NAO">NÃO</option>
        <option value="SIM">SIM</option>
      </select>

      <label>{placeholder}</label>

      {valorSelect === "SIM" && (
        <div className="campo">
          <input name={nomeResposta2} onChange={onChange} />
          <label>{placeholder2}</label>
        </div>
      )}
    </div>
  );
}

export { Inputf, Select };
