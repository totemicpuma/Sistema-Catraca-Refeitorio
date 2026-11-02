document.addEventListener("DOMContentLoaded", () => {
  const tabela = document.getElementById("turmas-table");
  if (!tabela) return;

  const filtroCurso = document.getElementById("filtro-curso");
  const filtroStatus = document.getElementById("filtro-status");
  const buscaAlunos = document.getElementById("busca-alunos-turma");
  const contador = document.getElementById("result-count");

  function filtrarTurmas() {
    const curso = (filtroCurso?.value || "").toLowerCase().trim();
    const status = filtroStatus?.value || "";
    const busca = (buscaAlunos?.value || "").trim().toLowerCase();
    let visiveis = 0;

    const linhas = tabela.querySelectorAll("tbody tr");
    linhas.forEach((linha) => {
      const cursoCelula = (linha.cells[1]?.textContent || "").toLowerCase().trim();
      const statusCelula = (linha.cells[3]?.textContent || "").toLowerCase().trim();
      const turmaCell = (linha.cells[0]?.querySelector("strong")?.textContent || "").trim();
      const turmaChave = (cursoCelula + "|" + turmaCell).toLowerCase();

      const matchCurso = !curso || cursoCelula.includes(curso);
      const matchStatus =
        !status ||
        (status === "liberada" && statusCelula.includes("liberada")) ||
        (status === "bloqueada" && statusCelula.includes("bloqueada"));

      // Busca por aluno: verifica se algum aluno dessa turma corresponde
      let matchAluno = true;
      if (busca && window.ALUNOS_DADOS) {
        matchAluno = window.ALUNOS_DADOS.some((a) => {
          const chaveAluno = (a.curso.trim() + "|" + a.turma.trim()).toLowerCase();
          if (chaveAluno !== turmaChave) return false;
          return (
            a.nome.trim().toLowerCase().includes(busca) ||
            a.matricula.trim().toLowerCase().includes(busca)
          );
        });
      }

      if (matchCurso && matchStatus && matchAluno) {
        linha.style.display = "";
        visiveis++;
      } else {
        linha.style.display = "none";
      }
    });

    if (contador) {
      const total = linhas.length;
      contador.textContent = `${visiveis} de ${total} turmas`;
    }

    const emptyRow = tabela.querySelector(".table-empty");
    if (visiveis === 0) {
      if (!emptyRow) {
        const row = document.createElement("tr");
        row.className = "table-empty-row";
        const cols = tabela.querySelector("thead tr")?.children?.length || 4;
        row.innerHTML = `<td colspan="${cols}" class="table-empty">${
          busca
            ? 'Nenhum aluno encontrado com "' + busca + '"'
            : "Nenhuma turma encontrada com esses filtros"
        }</td>`;
        tabela.querySelector("tbody").appendChild(row);
      }
    } else {
      tabela.querySelectorAll(".table-empty-row").forEach((r) => r.remove());
    }
  }

  filtroCurso?.addEventListener("change", filtrarTurmas);
  filtroStatus?.addEventListener("change", filtrarTurmas);
  buscaAlunos?.addEventListener("input", filtrarTurmas);

  // Iniciar filtros
  filtrarTurmas();
});
