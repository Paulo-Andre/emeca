import "../components/css/formulario.css";
import { useNavigate } from "react-router-dom";
import ProgressBar from "./progressBar";
import type { SetDados } from "../components/useState_SalvandoDados/salvandoDadosUseState";
import { salvaDados } from "../components/useState_SalvandoDados/salvandoDadosUseState";
import { useState } from "react";


type Props = {
  dado: SetDados;
  setDados: React.Dispatch<React.SetStateAction<SetDados>>;
};

export default function DadosMae({ dado, setDados }: Props) {
  const navigate = useNavigate();

  // 🔹 MÁSCARAS
  const mascaraCPF = (valor: string): string => {
    return valor
      .replace(/\D/g, "") // remove tudo que não é número
      .slice(0, 11) // limita a 11 dígitos
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
  };
  const validarCPF = (cpf: string): boolean => {
    cpf = cpf.replace(/\D/g, "");
  
    if (cpf.length !== 11 || /^(\d)\1+$/.test(cpf)) return false;
  
    let soma = 0;
    let resto;
  
    for (let i = 1; i <= 9; i++) {
      soma += parseInt(cpf[i - 1]) * (11 - i);
    }
  
    resto = (soma * 10) % 11;
    if (resto >= 10) resto = 0;
    if (resto !== parseInt(cpf[9])) return false;
  
    soma = 0;
    for (let i = 1; i <= 10; i++) {
      soma += parseInt(cpf[i - 1]) * (12 - i);
    }
  
    resto = (soma * 10) % 11;
    if (resto >= 10) resto = 0;
  
    return resto === parseInt(cpf[10]);
  };
  const [cpf, setCpf] = useState("");
  const [cpfErro, setCpfErro] = useState(false)
  
   const handleCPF = (e: React.ChangeEvent<HTMLInputElement>) => {
  const valor = mascaraCPF(e.target.value);

  setCpf(valor);

  const cpfLimpo = valor.replace(/\D/g, "");

  if (cpfLimpo.length < 11) {
    setCpfErro(true);
  } else {
    setCpfErro(!validarCPF(cpfLimpo));
  }

  // 🔥 FORÇA salvar no mesmo padrão dos outros inputs
  salvaDados(
    {
      ...e,
      target: {
        ...e.target,
        name: "cpfMae",
        value: valor, // salva com máscara
      },
    } as React.ChangeEvent<HTMLInputElement>,
    setDados
  );
};
  const mascaraTelefone = (valor: string) => {
    return valor
      .replace(/\D/g, "")
      .replace(/(\d{2})(\d)/, "($1) $2")
      .replace(/(\d{5})(\d)/, "$1-$2")
      .slice(0, 15);
  };

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    const form = e.currentTarget;

    if (form.checkValidity()) {
      navigate("/EstadoCivilDosPais");
    } else {
      form.reportValidity();
    }
  };

  return (
    <div className="formulario-page">
      <div className="formulario-container">

        {/* HEADER */}
        
        <header className="formulario-header">
                  <div className="header-brand">
                    <img src="logo_escola.svg" alt="Logo" className="header-logo" />
                    <div className="header-text">
                     <h1>Ficha de Matrícula</h1>
              <p>Dados da Mãe / Responsável</p>
                      
                    </div>
                  </div>
        
                  <ProgressBar etapaAtual={2} />
                </header>
        

        {/* FORM */}
        <div className="form-card">
          <form onSubmit={handleSubmit}>

            {/* A. IDENTIFICAÇÃO */}
            <div className="section-title">A. Dados da Mãe</div>

            <div className="form-grid">

              <div className="field">
                <label>Nome completo *</label>
                <input name="nomeMae" required onChange={(e) => salvaDados(e, setDados)} />
              </div>

              <div className="field">
                <label>Nacionalidade *</label>
                <input name="nacionalidadeMae" list="lista-nacionalidades" required onChange={(e) => salvaDados(e, setDados)} />
                
                <datalist id="lista-nacionalidades">
  <option value="Brasileiro">Brasileiro</option>
  <option value="Brasileira">Brasileira</option>
  <option value="Americano">Americano</option>
  <option value="Americana">Americana</option>
  <option value="Português">Português</option>
  <option value="Portuguesa">Portuguesa</option>
  <option value="Argentino">Argentino</option>
  <option value="Argentina">Argentina</option>
  <option value="Francês">Francês</option>
  <option value="Francesa">Francesa</option>
  <option value="Alemão">Alemão</option>
  <option value="Alemã">Alemã</option>
  <option value="Espanhol">Espanhol</option>
  <option value="Espanhola">Espanhola</option>
  <option value="Italiano">Italiano</option>
  <option value="Italiana">Italiana</option>
  <option value="Britânico">Britânico</option>
  <option value="Britânica">Britânica</option>
  <option value="Canadense">Canadense</option>
  <option value="Japonês">Japonês</option>
  <option value="Japonesa">Japonesa</option>
  <option value="Chinês">Chinês</option>
  <option value="Chinesa">Chinesa</option>
  <option value="Coreano">Coreano</option>
  <option value="Coreana">Coreana</option>
  <option value="Mexicano">Mexicano</option>
  <option value="Mexicana">Mexicana</option>
  <option value="Chileno">Chileno</option>
  <option value="Chilena">Chilena</option>
  <option value="Colombiano">Colombiano</option>
  <option value="Colombiana">Colombiana</option>
  <option value="Uruguaio">Uruguaio</option>
  <option value="Uruguaia">Uruguaia</option>
  <option value="Paraguaio">Paraguaio</option>
  <option value="Paraguaia">Paraguaia</option>
  <option value="Peruano">Peruano</option>
  <option value="Peruana">Peruana</option>
  <option value="Angolano">Angolano</option>
  <option value="Angolana">Angolana</option>
  <option value="Moçambicano">Moçambicano</option>
  <option value="Moçambicana">Moçambicana</option>
  <option value="Sul-africano">Sul-africano</option>
  <option value="Sul-africana">Sul-africana</option>
  <option value="Indiano">Indiano</option>
  <option value="Indiana">Indiana</option>
  <option value="Australiano">Australiano</option>
  <option value="Australiana">Australiana</option>
  <option value="Neozelandês">Neozelandês</option>
  <option value="Neozelandesa">Neozelandesa</option>
  <option value="Suíço">Suíço</option>
  <option value="Suíça">Suíça</option>
  <option value="Belga">Belga</option>
  <option value="Holandês">Holandês</option>
  <option value="Holandesa">Holandesa</option>
  <option value="Sueco">Sueco</option>
  <option value="Sueca">Sueca</option>
  <option value="Norueguês">Norueguês</option>
  <option value="Norueguesa">Norueguesa</option>
  <option value="Dinamarquês">Dinamarquês</option>
  <option value="Dinamarquesa">Dinamarquesa</option>
  <option value="Finlandês">Finlandês</option>
  <option value="Finlandesa">Finlandesa</option>
  <option value="Russo">Russo</option>
  <option value="Russa">Russa</option>
  <option value="Turco">Turco</option>
  <option value="Turca">Turca</option>
  <option value="Saudita">Saudita</option>
  <option value="Emiratense">Emiratense</option>
  <option value="Israelense">Israelense</option>
</datalist>
              </div>

              <div className="field">
                <label>Naturalidade *</label>
                <input name="naturalidadeMae" required onChange={(e) => salvaDados(e, setDados)} />
              </div>

              
              
              <div className="field">
                <label htmlFor=""> UF*</label>
              
              <select name="ufMae"
  required
  
  onChange={(e) => salvaDados(e, setDados)}
>
  
  <option value="">Selecione</option>
  <option value="MG">Minas Gerais</option>

  <option value="AC">Acre</option>
  <option value="AL">Alagoas</option>
  <option value="AP">Amapá</option>
  <option value="AM">Amazonas</option>
  <option value="BA">Bahia</option>
  <option value="CE">Ceará</option>
  <option value="DF">Distrito Federal</option>
  <option value="ES">Espírito Santo</option>
  <option value="GO">Goiás</option>
  <option value="MA">Maranhão</option>
  <option value="MT">Mato Grosso</option>
  <option value="MS">Mato Grosso do Sul</option>
  <option value="PA">Pará</option>
  <option value="PB">Paraíba</option>
  <option value="PR">Paraná</option>
  <option value="PE">Pernambuco</option>
  <option value="PI">Piauí</option>
  <option value="RJ">Rio de Janeiro</option>
  <option value="RN">Rio Grande do Norte</option>
  <option value="RS">Rio Grande do Sul</option>
  <option value="RO">Rondônia</option>
  <option value="RR">Roraima</option>
  <option value="SC">Santa Catarina</option>
  <option value="SP">São Paulo</option>
  <option value="SE">Sergipe</option>
  <option value="TO">Tocantins</option>
</select>
</div>

              <div className="field">
                <label>Data de nascimento *</label>
                <input type="date" name="dataDeNascimentoMae" required onChange={(e) => salvaDados(e, setDados)} />
              </div>

              <div className="field">
                <label>Profissão *</label>
                <input name="profissaoMae" required onChange={(e) => salvaDados(e, setDados)} />
              </div>

            </div>

            {/* B. DOCUMENTOS */}
            <div className="section-title">B. Documentos</div>

            <div className="form-grid">

              <div className="field">
                <label>CPF *</label>
                <input
                  name="cpfMae"
                  required
                 value={cpf}
                  onChange={handleCPF}
  style={{
      border: cpfErro ? "2px solid red" : "1px solid #ccc",
    }}
  />

  {cpfErro && (
    <small style={{ color: "red" }}>
      CPF inválido
    </small>
  )}
</div>

              <div className="field">
                <label>RG </label>
                <input type="text" name="rgMae"  onChange={(e) => salvaDados(e, setDados)} />
              </div>

              <div className="field">
                <label>Órgão emissor </label>
                <input name="orgaoEmissorMae" onChange={(e) => salvaDados(e, setDados)} />
              </div>

              <div className="field">
                <label>Data de expedição </label>
                <input type="date" name="dataExpedicaoMae" onChange={(e) => salvaDados(e, setDados)} />
              </div>

            </div>

            {/* C. CONTATO */}
            <div className="section-title">C. Contato</div>

            <div className="form-grid">

              <div className="field">
                <label>Telefone *</label>
                <input
                  name="telefoneMae"
                  required
                  onChange={(e) => {
                    e.target.value = mascaraTelefone(e.target.value);
                    salvaDados(e, setDados);
                  }}
                />
              </div>

              <div className="field">
                <label>WhatsApp *</label>
                <input
                  name="whatsappMae"
                  required
                  onChange={(e) => {
                    e.target.value = mascaraTelefone(e.target.value);
                    salvaDados(e, setDados);
                  }}
                />
              </div>

            </div>

            {/* BOTÕES */}
            <div className="form-actions">

              <button
                type="button"
                className="btn-next"
                onClick={() => navigate(-1)}
                style={{ background: "#64748b" }}
              >
                Voltar
              </button>

              <button type="submit" className="btn-next">
                Próximo
              </button>

            </div>

          </form>
        </div>
      </div>
    </div>
  );
}