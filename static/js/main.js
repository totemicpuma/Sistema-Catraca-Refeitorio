// Sistema do Refeitório — Core Functions (Tema, Modais, Toast, Utilitários)

document.addEventListener("DOMContentLoaded", () => {
  // === TOAST: Converte flash messages antigas em toasts ===
  document.querySelectorAll("#flash-container .toast").forEach((toast) => {
    mostrarToast(toast.textContent.trim(), toast.className.replace("toast ", ""));
    toast.remove();
  });
});

// === TEMA ===
function trocarTema() {
  fetch("/toggle-theme").then(() => location.reload());
}

// === MODAIS ===
function abrirModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.style.display = "flex";
    modal.classList.add("active");
    document.body.style.overflow = "hidden";
  }
}

function fecharModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.style.display = "none";
    modal.classList.remove("active");
    document.body.style.overflow = "";
  }
}

function abrirConfiguracoes() { abrirModal("config-modal"); }
function fecharConfiguracoes() { fecharModal("config-modal"); }
function abrirLogout() { abrirModal("logout-modal"); }
function fecharLogout() { fecharModal("logout-modal"); }

// Fechar modais ao clicar fora
document.addEventListener("click", (e) => {
  if (e.target.classList.contains("modal-overlay") && e.target.style.display !== "none") {
    e.target.style.display = "none";
    e.target.classList.remove("active");
    document.body.style.overflow = "";
  }
});

// Fechar modais com Escape
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    document.querySelectorAll(".modal-overlay.active").forEach((modal) => {
      modal.style.display = "none";
      modal.classList.remove("active");
    });
    document.querySelectorAll(".filter-dropdown.visivel").forEach((d) => {
      d.classList.remove("visivel");
      d.previousElementSibling?.classList.remove("ativo");
    });
    document.body.style.overflow = "";
  }
});

// === FILTRO FUNIL ===
function toggleFiltros(btn) {
  const dropdown = btn.nextElementSibling;
  const visivel = dropdown.classList.contains("visivel");
  document.querySelectorAll(".filter-dropdown.visivel").forEach((d) => {
    d.classList.remove("visivel");
    d.previousElementSibling?.classList.remove("ativo");
  });
  if (!visivel) {
    dropdown.classList.add("visivel");
    btn.classList.add("ativo");
  }
}

document.addEventListener("click", (e) => {
  if (!e.target.closest(".filter-wrapper")) {
    document.querySelectorAll(".filter-dropdown.visivel").forEach((d) => {
      d.classList.remove("visivel");
      d.previousElementSibling?.classList.remove("ativo");
    });
  }
});

// === TOAST ===
function mostrarToast(mensagem, tipo = "info", duracao = 4000) {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${tipo}`;
  const tipos = { sucesso: "success", erro: "error", error: "error", danger: "error", info: "info", warning: "warning" };
  const tipoFinal = tipos[tipo] || "info";
  toast.className = `toast toast-${tipoFinal}`;
  toast.textContent = mensagem;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("toast-out");
    setTimeout(() => toast.remove(), 300);
  }, duracao);
}

// === SKELETON LOADING ===
function mostrarSkeleton(containerId, tipo = "kpi") {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (tipo === "kpi") {
    container.innerHTML = `
      <div class="skeleton skeleton-kpi"></div>
      <div class="skeleton skeleton-kpi"></div>
      <div class="skeleton skeleton-kpi"></div>
      <div class="skeleton skeleton-kpi"></div>
    `;
  } else if (tipo === "chart") {
    container.innerHTML = `<div class="skeleton skeleton-chart"></div>`;
  } else if (tipo === "table") {
    let html = "";
    for (let i = 0; i < 5; i++) {
      html += `<div class="skeleton skeleton-text" style="width:${Math.random() * 40 + 40}%"></div>`;
    }
    container.innerHTML = html;
  }
}

// === CONTADOR ANIMADO ===
function animarContador(elemento, valorFinal, duracao = 600) {
  if (!elemento) return;
  const valorAtual = parseInt(elemento.textContent) || 0;
  const incremento = (valorFinal - valorAtual) / (duracao / 16);
  let atual = valorAtual;

  elemento.classList.add("count-animate");

  const animar = () => {
    atual += incremento;
    if ((incremento > 0 && atual >= valorFinal) || (incremento < 0 && atual <= valorFinal)) {
      elemento.textContent = valorFinal;
      elemento.classList.remove("count-animate");
      return;
    }
    elemento.textContent = Math.round(atual);
    requestAnimationFrame(animar);
  };

  requestAnimationFrame(animar);
}

// === FORMATAÇÃO ===
function formatarData(data) {
  return new Date(data).toLocaleDateString("pt-BR");
}

function formatarHora(data) {
  if (!data) return "-- : --";
  if (typeof data === "string") return data;
  return new Date(data).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

// === TABELA SORT ===
function ordenarTabela(table, colIndex) {
  const tbody = table.querySelector("tbody");
  const rows = Array.from(tbody.querySelectorAll("tr"));
  const ths = table.querySelectorAll("thead th");

  const isAsc = ths[colIndex].classList.contains("asc");
  ths.forEach((th) => th.classList.remove("asc", "desc"));

  ths[colIndex].classList.add(isAsc ? "desc" : "asc");

  const sorted = rows.sort((a, b) => {
    const aVal = a.cells[colIndex]?.textContent.trim() || "";
    const bVal = b.cells[colIndex]?.textContent.trim() || "";
    const aNum = parseFloat(aVal.replace(/[^\d,-]/g, "").replace(",", "."));
    const bNum = parseFloat(bVal.replace(/[^\d,-]/g, "").replace(",", "."));

    if (!isNaN(aNum) && !isNaN(bNum)) {
      return isAsc ? bNum - aNum : aNum - bNum;
    }
    return isAsc ? bVal.localeCompare(aVal, "pt-BR") : aVal.localeCompare(bVal, "pt-BR");
  });

  sorted.forEach((row) => tbody.appendChild(row));
}

// Inicializar sortable tables
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("table.sortable thead th").forEach((th, index) => {
    th.classList.add("sortable");
    th.style.cursor = "pointer";
    th.addEventListener("click", () => {
      const table = th.closest("table");
      ordenarTabela(table, index);
    });
  });
});
