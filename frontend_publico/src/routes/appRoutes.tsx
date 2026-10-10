import { Routes, Route ,Navigate} from "react-router-dom";
import { useState } from "react";
import { estadoInicial } from "../components/useState_SalvandoDados/salvandoDadosUseState";


import DadosPai from "../pages/dadosPai";
import DadosMae from "../pages/dadosMae";
import EstadoCivil from "../pages/estadoCivil";
import DadosResponsavelLegal from "../pages/dadosResposanvel";
import DadosEndereco from "../pages/dadosEndereco";
import DadosHistoticoCrianca from "../pages/dadosHistocidodacrianca";
import DadosAluno from "../pages/indexMatricula";
import MatriculaFim from "../pages/matriculaFim";
import DuvidasMatricula from "../pages/duvidasMatricula";
export default function AppRoutes() {
  const [dado, setDados] = useState(estadoInicial);

  return (
    <Routes>
      <Route path="/Matricula" element={<DadosAluno dado={dado} setDados={setDados}/>  }  /> 

      
      <Route
        path="/DadosPai"
        element={<DadosPai dado={dado} setDados={setDados} />}
      />

      <Route
        path="/DadosMae"
        element={<DadosMae dado={dado} setDados={setDados} />}
      />

      <Route
        path="/EstadoCivilDosPais"
        element={<EstadoCivil dado={dado} setDados={setDados} />}
      />

      <Route
        path="/DadosResponsavel"
        element={<DadosResponsavelLegal dado={dado} setDados={setDados} />}
      />

      <Route
        path="/Endereco"
        element={<DadosEndereco dado={dado} setDados={setDados} />}
      />

      <Route
        path="/HistoricoDaCrianca"
        element={<DadosHistoticoCrianca dado={dado} setDados={setDados} />}
      />

      <Route path="/sucesso" element={<MatriculaFim />} />
      <Route
        path="/"
        element={<DuvidasMatricula />}
        
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
