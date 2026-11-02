// Dashboard Executivo — Gráficos, KPIs, Analytics
// Acessível para todas as idades: cores de alto contraste, labels claras, animações suaves

const CORES = () => ({
  green: isDark() ? "#34d399" : "#0d9668",
  greenLight: isDark() ? "rgba(52, 211, 153, 0.35)" : "rgba(13, 150, 104, 0.35)",
  blue: isDark() ? "#38bdf8" : "#1d4ed8",
  blueLight: isDark() ? "rgba(56, 189, 248, 0.35)" : "rgba(29, 78, 216, 0.35)",
  red: isDark() ? "#f87171" : "#dc2626",
  yellow: isDark() ? "#fbbf24" : "#d97706",
  purple: isDark() ? "#a78bfa" : "#7c3aed",
  orange: isDark() ? "#fb923c" : "#ea580c",
  cyan: isDark() ? "#22d3ee" : "#0891b2",
  pink: isDark() ? "#f472b6" : "#db2777",
});

const CORES_PALETA = () => isDark()
  ? ["#34d399", "#38bdf8", "#a78bfa", "#fbbf24", "#fb923c", "#f87171", "#22d3ee", "#f472b6", "#a3e635", "#2dd4bf"]
  : ["#0d9668", "#1d4ed8", "#7c3aed", "#d97706", "#ea580c", "#dc2626", "#0891b2", "#db2777", "#65a30d", "#0e7490"];

// Chart.js defaults globais para acessibilidade
Chart.defaults.font.family = "'Segoe UI', system-ui, -apple-system, sans-serif";
Chart.defaults.font.size = 15;
Chart.defaults.color = "#1b1f26";
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.padding = 14;
Chart.defaults.plugins.legend.labels.boxWidth = 12;

const isDark = () => document.body.classList.contains("dark-mode");
const textColor = () => isDark() ? "#e2e6ea" : "#1b1f26";
const gridColor = () => isDark() ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.08)";
const chartFont = (size) => ({ font: { size }, color: textColor() });

Chart.defaults.locale = 'pt-BR';
Chart.register({
  id: 'noDataText',
  beforeDraw(chart) {
    if (chart.data.datasets.length === 0 || chart.data.datasets.every(ds => ds.data.length === 0)) {
      const ctx = chart.ctx;
      chart.clear();
      ctx.save();
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.font = '14px "Segoe UI", sans-serif';
      ctx.fillStyle = textColor();
      ctx.fillText('Sem dados', chart.width / 2, chart.height / 2);
      ctx.restore();
    }
  }
});

// Sobrescrever para dark mode via MutationObserver
const observer = new MutationObserver(() => {
  Chart.defaults.color = textColor();
  // Redesenhar gráficos com novas cores
  Object.keys(window).filter(k => k.startsWith("chart")).forEach(k => {
    const chart = window[k];
    if (chart && chart.options) {
      chart.options.color = textColor();
      chart.options.scales?.y && (chart.options.scales.y.grid.color = gridColor());
      chart.options.scales?.x && (chart.options.scales.x.grid.color = gridColor());
      chart.options.scales?.r && (chart.options.scales.r.grid.color = gridColor());
      chart.update();
    }
  });
});
observer.observe(document.body, { attributes: true, attributeFilter: ["class"] });

// === CARREGAR TODOS OS DADOS ===
async function carregarDashboard() {
  try {
    const [dashRes, analyticsRes] = await Promise.all([
      fetch("/api/dashboard_dados"),
      fetch("/api/analytics_dados"),
    ]);
    const dash = await dashRes.json();
    const analytics = await analyticsRes.json();
    atualizarKPIs(dash);
    renderizarGraficoFluxoHora(dash.fluxo_por_hora);
    renderizarGraficoComparativo(dash.comparativo_semanal);
    renderizarGraficoDiaSemana(analytics.dia_semana_acessos);
    renderizarInsights(dash.insights);
    renderizarPico(dash.pico_hoje, analytics.refeicoes_7d);
  } catch (error) {
    console.error("Erro ao carregar dashboard:", error);
    mostrarToast("Erro ao carregar dados do dashboard", "error");
  }
}

// === ATUALIZAR KPIs ===
function atualizarKPIs(data) {
  const kpis = [
    { id: "kpi-total-alunos", valor: data.total_alunos, label: "Total de alunos cadastrados", icon: "👥" },
    { id: "kpi-registros-hoje", valor: data.registros_hoje, label: "Passagens registradas hoje", icon: "🍽️" },
    { id: "kpi-media-diaria", valor: data.media_diaria, label: "Média diária (7 dias)", icon: "📊" },
    { id: "kpi-pico-hoje", valor: data.pico_hoje?.maximo || 0, label: "Passagens na hora de pico", icon: "⚡" },
  ];

  const grid = document.getElementById("kpi-grid");
  if (!grid) return;

  grid.innerHTML = kpis
    .map(
      ({ id, valor, label, icon }) => `
    <div class="kpi-card" role="region" aria-label="${label}">
      <div class="kpi-icon" style="background:var(--green-light);color:var(--green)" aria-hidden="true">${icon}</div>
      <span class="kpi-valor" id="${id}" aria-live="polite">${valor}</span>
      <p>${label}</p>
    </div>
  `
    )
    .join("");
}

// === GRÁFICO: FLUXO POR HORA ===
function renderizarGraficoFluxoHora(dados) {
  const canvas = document.getElementById("chart-fluxo-hora");
  if (!canvas || !dados) return;
  const ctx = canvas.getContext("2d");
  if (window.chartFluxoHora) window.chartFluxoHora.destroy();

  canvas.style.display = "block";
  const container = document.getElementById("chart-fluxo-container");
  const skeleton = container?.querySelector(".skeleton");
  if (skeleton) skeleton.style.display = "none";

  window.chartFluxoHora = new Chart(ctx, {
    type: "bar",
    data: {
      labels: dados.map((d) => d.hora),
      datasets: [
        {
          label: "Passagens",
          data: dados.map((d) => d.entradas),
          backgroundColor: isDark() ? "rgba(52, 211, 153, 0.35)" : "rgba(13, 150, 104, 0.4)",
          borderColor: CORES().green,
          borderWidth: 2,
          borderRadius: 4,
          borderSkipped: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      color: textColor(),
      plugins: {
        legend: { position: "top", labels: { font: { size: 14 }, color: textColor() } },
        tooltip: { 
          bodyFont: { size: 14 },
          titleFont: { size: 14 },
        },
      },
      scales: {
        y: { beginAtZero: true, ticks: { precision: 0, ...chartFont(14) }, grid: { color: gridColor() } },
        x: { grid: { display: false }, ticks: chartFont(14) },
      },
    },
  });
}



// === GRÁFICO: COMPARATIVO SEMANAL ===
function renderizarGraficoComparativo(dados) {
  const canvas = document.getElementById("chart-comparativo");
  if (!canvas || !dados) return;
  const ctx = canvas.getContext("2d");
  if (window.chartComparativo) window.chartComparativo.destroy();

  canvas.style.display = "block";
  const skeleton = canvas.parentElement?.querySelector(".skeleton");
  if (skeleton) skeleton.style.display = "none";

  window.chartComparativo = new Chart(ctx, {
    type: "line",
    data: {
      labels: dados.map((d) => d.dia),
      datasets: [
        {
          label: "Esta semana",
          data: dados.map((d) => d.esta_semana),
          borderColor: CORES().green,
          backgroundColor: (ctx) => {
            const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, 200);
            g.addColorStop(0, isDark() ? "rgba(52,211,153,0.25)" : "rgba(13,150,104,0.3)");
            g.addColorStop(1, "rgba(13,150,104,0)");
            return g;
          },
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointHoverRadius: 7,
          borderWidth: 2.5,
        },
        {
          label: "Semana anterior",
          data: dados.map((d) => d.semana_anterior),
          borderColor: CORES().blue,
          backgroundColor: "transparent",
          fill: false,
          tension: 0.4,
          borderDash: [5, 3],
          pointRadius: 3,
          pointHoverRadius: 6,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      color: textColor(),
      interaction: { intersect: false, mode: "index" },
      plugins: {
        legend: { position: "top", labels: { font: { size: 14 }, padding: 14, color: textColor() } },
        tooltip: { bodyFont: { size: 14 }, titleFont: { size: 14 } },
      },
      scales: {
        y: { beginAtZero: true, ticks: { precision: 0, ...chartFont(14) }, grid: { color: gridColor() } },
        x: { grid: { display: false }, ticks: chartFont(14) },
      },
    },
  });
}

// === GRÁFICO: ACESSOS POR DIA DA SEMANA ===
function renderizarGraficoDiaSemana(dados) {
  const canvas = document.getElementById("chart-dia-semana");
  if (!canvas || !dados) return;
  const ctx = canvas.getContext("2d");
  if (window.chartDiaSemana) window.chartDiaSemana.destroy();

  canvas.style.display = "block";
  const skeleton = canvas.parentElement?.querySelector(".skeleton");
  if (skeleton) skeleton.style.display = "none";

  window.chartDiaSemana = new Chart(ctx, {
    type: "bar",
    data: {
      labels: dados.map((d) => d.dia),
      datasets: [{
        label: "Acessos",
        data: dados.map((d) => d.total),
        backgroundColor: dados.map((_, i) => {
          const c = CORES_PALETA()[i % CORES_PALETA().length];
          return isDark() ? c + "55" : c + "55";
        }),
        borderColor: dados.map((_, i) => CORES_PALETA()[i % CORES_PALETA().length]),
        borderWidth: 1.5,
        borderRadius: 4,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      color: textColor(),
      plugins: {
        legend: { display: false },
        tooltip: { bodyFont: { size: 14 } },
      },
      scales: {
        y: { beginAtZero: true, ticks: { precision: 0, ...chartFont(14) }, grid: { color: gridColor() } },
        x: { grid: { display: false }, ticks: { ...chartFont(14), weight: "bold" } },
      },
    },
  });
}

// === INSIGHTS ===
function renderizarInsights(insights) {
  const container = document.getElementById("insights-container");
  if (!container) return;

  if (!insights || insights.length === 0) {
    container.innerHTML = '<div class="card card-subtle" style="padding:12px 16px"><p style="color:var(--text-muted);font-style:italic">Aguardando dados...</p></div>';
    return;
  }

  container.innerHTML = insights
    .map(
      (item) => `
    <div class="card card-subtle" style="padding:14px 18px;animation:slideUp 0.3s ease" role="listitem">
      <p style="font-size:var(--text-sm);color:var(--text-muted);margin-bottom:4px;font-weight:var(--weight-bold)">${item.label}</p>
      <p style="font-size:var(--text-base);font-weight:var(--weight-semibold);color:var(--text-secondary);line-height:var(--leading-relaxed)">${item.valor}</p>
    </div>
  `
    )
    .join("");
}

// === PICO DE HOJE + REFEIÇÕES ===
function renderizarPico(pico, refeicoes) {
  const el = document.getElementById("pico-info");
  if (!el) return;

  const listaRefeicoes = (refeicoes || []).length
    ? refeicoes
        .map(
          (r) => `
        <div style="display:flex;justify-content:space-between;font-size:var(--text-sm);padding:2px 0">
          <span style="color:var(--text-secondary)">${r.refeicao}</span>
          <strong style="color:var(--blue)">${r.total}</strong>
        </div>`
        )
        .join("")
    : `<p style="font-size:var(--text-sm);color:var(--text-muted)">Sem registros</p>`;

  el.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div style="background:var(--bg-subtle);border-radius:var(--radius-sm);padding:16px;text-align:center;border:1px solid var(--border-soft)">
        <p style="font-size:var(--text-sm);font-weight:var(--weight-bold);color:var(--text-muted);margin-bottom:8px">Hora de Pico</p>
        <p style="font-size:var(--text-4xl);font-weight:var(--weight-extrabold);color:var(--green)">${pico.maximo}</p>
        <p style="font-size:var(--text-sm);color:var(--text-secondary)">passagens às ${pico.horario || "--:--"}</p>
      </div>
      <div style="background:var(--bg-subtle);border-radius:var(--radius-sm);padding:16px;border:1px solid var(--border-soft)">
        <p style="font-size:var(--text-sm);font-weight:var(--weight-bold);color:var(--text-muted);margin-bottom:8px;text-align:center">Por Refeição (7 dias)</p>
        ${listaRefeicoes}
      </div>
    </div>
  `;
}

// Inicializar
document.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("kpi-grid")) {
    carregarDashboard();
  }
});
