let fluxoInterval = null;
let todosLogs = [];
let searchTerm = "";
let searchTimeout = null;
let filtroCurso = "";

function iniciarFluxo() {
  atualizarFluxo();
  fluxoInterval = setInterval(atualizarFluxo, 3000);
  configurarBusca();
}

function pararFluxo() {
  if (fluxoInterval) { clearInterval(fluxoInterval); fluxoInterval = null; }
}

function configurarBusca() {
  const input = document.getElementById("busca-aluno");
  if (!input) return;
  input.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      searchTerm = input.value.trim().toLowerCase();
      aplicarFiltro();
    }, 200);
  });
}

function preencherCursos(cursos) {
  const select = document.getElementById("filtro-curso");
  if (!select || !cursos) return;
  const atual = select.value;
  select.innerHTML = '<option value="">Todos os Cursos</option>';
  cursos.forEach(c => {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    select.appendChild(opt);
  });
  if (atual) select.value = atual;
}

function aplicarFiltro() {
  const tabela = document.getElementById("tabela-logs");
  if (!tabela) return;

  filtroCurso = document.getElementById("filtro-curso")?.value || "";

  const rows = tabela.querySelectorAll("tr");
  let visible = 0;
  rows.forEach((row) => {
    if (row.classList.contains("table-empty")) return;
    const nome = row.cells?.[0]?.textContent?.toLowerCase() || "";
    const matricula = row.dataset.matricula?.toLowerCase() || "";
    const curso = row.dataset.curso || "";

    const buscaOk = !searchTerm || nome.includes(searchTerm) || matricula.includes(searchTerm);
    const cursoOk = !filtroCurso || curso === filtroCurso;

    if (buscaOk && cursoOk) {
      row.style.display = "";
      visible++;
    } else {
      row.style.display = "none";
    }
  });

  const emptyRow = tabela.querySelector(".table-empty");
  if (visible === 0 && !emptyRow) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="4" class="table-empty">Nenhum resultado encontrado</td>`;
    tabela.appendChild(tr);
  } else if (visible > 0 && emptyRow) {
    emptyRow.remove();
  }
}

function atualizarTimeline(logs) {
  const container = document.getElementById("timeline-bars");
  if (!container) return;

  const horas = {};
  for (let h = 6; h < 20; h++) {
    horas[`${String(h).padStart(2, "0")}`] = 0;
  }

  logs.forEach(log => {
    if (log.entrada_raw) {
      const h = new Date(log.entrada_raw).getHours().toString().padStart(2, "0");
      if (horas[h] !== undefined) horas[h]++;
    }
  });

  const maxVal = Math.max(...Object.values(horas), 1);

  container.innerHTML = "";
  Object.entries(horas).forEach(([h, total]) => {
    const pct = total / maxVal;
    const altura = Math.max(pct * 36, 2);
    let cor = "#E5E7EB";
    if (total > 0) {
      if (pct > 0.6) cor = "#DC2626";
      else if (pct > 0.3) cor = "#F59E0B";
      else cor = "#0D9668";
    }
    const div = document.createElement("div");
    div.style.cssText = "flex:1;display:flex;flex-direction:column;align-items:center";
    div.innerHTML = `
      <div class="timeline-bar" style="height:${altura}px;background:${cor}"></div>
      <div class="timeline-label">${h}h</div>
    `;
    container.appendChild(div);
  });
}

async function atualizarFluxo() {
  try {
    const response = await fetch("/api/fluxo_dados");
    const data = await response.json();

    todosLogs = data.logs || [];
    atualizarTimeline(todosLogs);

    const totalHoje = document.getElementById("total-hoje");
    if (totalHoje) totalHoje.textContent = data.total_hoje;

    const elUnicos = document.getElementById("alunos-unicos");
    if (elUnicos) elUnicos.textContent = data.alunos_unicos;

    const elRefeicao = document.getElementById("refeicao-atual");
    if (elRefeicao) elRefeicao.textContent = data.refeicao_atual || "Nenhuma";

    preencherCursos(data.cursos);

    const tabela = document.getElementById("tabela-logs");
    if (!tabela) return;

    // A chave tem que ser o id do registro, não a matrícula: um aluno pode
    // passar em mais de uma refeição no mesmo dia, então a matrícula se repete
    // em várias linhas.
    const idsAtuais = new Set(data.logs.map(l => String(l.id)));

    Array.from(tabela.children).forEach((row) => {
      const id = row.dataset.id;
      if (id && !idsAtuais.has(id)) {
        row.style.transition = "opacity 0.3s";
        row.style.opacity = "0";
        setTimeout(() => row.remove(), 300);
      }
    });

    // Uma passagem é imutável depois de registrada: só precisamos inserir as
    // linhas novas, nunca atualizar as existentes.
    data.logs.forEach((log) => {
      if (tabela.querySelector(`[data-id="${log.id}"]`)) return;

      const row = criarLinha(log);
      row.style.animation = "slideIn 0.3s ease-out";
      if (tabela.firstChild) {
        tabela.insertBefore(row, tabela.firstChild);
      } else {
        tabela.appendChild(row);
      }
    });

    aplicarFiltro();

    if (data.logs.length === 0) {
      const emptyRow = tabela.querySelector(".table-empty");
      if (!emptyRow) {
        tabela.innerHTML = `<tr><td colspan="4" class="table-empty">Nenhuma passagem registrada hoje</td></tr>`;
      }
    }
  } catch (error) {
    console.error("Erro ao atualizar fluxo:", error);
  }
}

function criarLinha(log) {
  const tr = document.createElement("tr");
  tr.dataset.id = log.id;
  tr.dataset.matricula = log.matricula;
  tr.dataset.curso = log.curso || "";

  tr.innerHTML = `
    <td><strong>${log.nome}</strong></td>
    <td><span style="font-size:var(--text-xs);color:var(--text-muted)">${log.curso || '—'} ${log.turma ? '— ' + log.turma + 'º' : ''}</span></td>
    <td>${log.entrada}</td>
    <td><span class="badge badge-neutral">${log.refeicao || '—'}</span></td>
  `;

  return tr;
}

document.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("tabela-logs")) {
    iniciarFluxo();
    window.addEventListener("beforeunload", pararFluxo);
  }
});
