function getModal(id) {
    return bootstrap.Modal.getOrCreateInstance(document.getElementById(id));
}

function loadListaAgendamentos(dia, params) {
    params = params || {};
    const url = new URL(`/dia/${dia}/agendamentos/`, window.location.origin);
    Object.keys(params).forEach((k) => {
        if (params[k]) url.searchParams.set(k, params[k]);
    });
    fetch(url).then((r) => r.text()).then((html) => {
        document.getElementById("modalListaContent").innerHTML = html;
        getModal("modalLista").show();
    });
}

function loadCadastroAgenda(agendaId, extraParams) {
    let url;
    if (agendaId) {
        url = `/agenda/${agendaId}/editar/`;
    } else {
        url = "/agenda/nova/" + (extraParams ? `?${extraParams}` : "");
    }
    fetch(url).then((r) => r.text()).then((html) => {
        document.getElementById("modalCadastroContent").innerHTML = html;
        const listaEl = document.getElementById("modalLista");
        const listaInstance = bootstrap.Modal.getInstance(listaEl);
        if (listaInstance) listaInstance.hide();
        getModal("modalCadastro").show();
        initCadastroForm();
    });
}

function loadMedicoForm(medicoId) {
    const url = medicoId ? `/medicos/${medicoId}/editar/` : "/medicos/novo/";
    fetch(url).then((r) => r.text()).then((html) => {
        document.getElementById("modalMedicoContent").innerHTML = html;
        getModal("modalMedico").show();
    });
}

function loadConciergeForm(usuarioId) {
    const url = usuarioId ? `/cadastros/concierges/${usuarioId}/editar/` : "/cadastros/concierges/novo/";
    fetch(url).then((r) => r.text()).then((html) => {
        document.getElementById("modalConciergeContent").innerHTML = html;
        getModal("modalConcierge").show();
    });
}

function initSidebarToggle() {
    const sidebar = document.getElementById("appSidebar");
    const botao = document.getElementById("btn-toggle-sidebar");
    if (!sidebar || !botao) return;

    let recolhida = false;
    try {
        recolhida = localStorage.getItem("virtu-sidebar-recolhida") === "1";
    } catch (e) {}
    sidebar.classList.toggle("collapsed", recolhida);

    botao.addEventListener("click", function () {
        const agoraRecolhida = sidebar.classList.toggle("collapsed");
        try {
            localStorage.setItem("virtu-sidebar-recolhida", agoraRecolhida ? "1" : "0");
        } catch (e) {}
    });
}

document.addEventListener("DOMContentLoaded", initSidebarToggle);

function filtrarPorUnidade(unidadeId) {
    document.querySelectorAll("#id_sala option[data-unidade]").forEach((opt) => {
        opt.hidden = !(!unidadeId || opt.dataset.unidade === unidadeId);
    });
    // Médicos podem atender em várias unidades (data-unidades="1,3").
    document.querySelectorAll("option[data-unidades]").forEach((opt) => {
        opt.hidden = !unidadeId || !opt.dataset.unidades.split(",").includes(unidadeId);
    });
    // Sala e médicos dependem da unidade: ficam bloqueados até ela ser escolhida.
    document.querySelectorAll("select[data-depende-unidade]").forEach((sel) => {
        sel.disabled = !unidadeId;
        if (!unidadeId || (sel.selectedOptions[0] && sel.selectedOptions[0].hidden)) {
            sel.value = "";
        }
    });
    atualizarCamposMedico();
    document.querySelectorAll('select[name="procedimento[]"]').forEach((sel) => {
        sel.querySelectorAll("option[data-unidade]").forEach((opt) => {
            opt.hidden = !(!unidadeId || opt.dataset.unidade === unidadeId);
        });
    });
}

// Status do médico inicial: só existe com médico escolhido; o substituto só é liberado
// quando o inicial cancela, e o "Confirmado" do substituto só com um substituto escolhido.
function atualizarCamposMedico() {
    const unidadeSelect = document.getElementById("id_unidade");
    const inicial = document.getElementById("id_medico_inicial");
    const substituto = document.getElementById("id_medico_substituto");
    const substitutoConfirmado = document.getElementById("substituto_confirmado");
    if (!inicial || !substituto || !substitutoConfirmado) return;

    const temInicial = !!inicial.value;
    document.querySelectorAll('[name="medico_inicial_status"]').forEach((radio) => {
        radio.disabled = !temInicial;
        if (!temInicial) radio.checked = false;
    });

    // O inicial não pode ser o próprio substituto.
    substituto.querySelectorAll("option[data-unidades]").forEach((opt) => {
        if (opt.value === inicial.value) opt.hidden = true;
    });
    if (substituto.selectedOptions[0] && substituto.selectedOptions[0].hidden) substituto.value = "";

    const cancelado = temInicial && document.getElementById("status_cancelado").checked;
    substituto.disabled = !cancelado || !(unidadeSelect && unidadeSelect.value);
    if (!cancelado) substituto.value = "";

    substitutoConfirmado.disabled = substituto.disabled || !substituto.value;
    if (substitutoConfirmado.disabled) substitutoConfirmado.checked = false;

    const ajuda = document.getElementById("ajuda-substituto");
    if (ajuda) ajuda.hidden = cancelado;
}

function initCadastroForm() {
    const unidadeSelect = document.getElementById("id_unidade");
    if (unidadeSelect) {
        filtrarPorUnidade(unidadeSelect.value);
    }
    initFrequenciaToggle();
    atualizarAvisoRecorrencia();
    recalcularValores();
}

function formatarMoeda(valor) {
    return "R$ " + valor.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function recalcularValores() {
    const previstoEl = document.getElementById("valor-previsto");
    const realEl = document.getElementById("valor-real");
    if (!previstoEl || !realEl) return;

    const porProcedimento = document.getElementById("calc_procedimento")
        ? document.getElementById("calc_procedimento").checked
        : true;

    let totalPrevisto = 0;
    let totalReal = 0;
    document.querySelectorAll(".linha-procedimento").forEach((linha) => {
        const select = linha.querySelector('select[name="procedimento[]"]');
        const opt = select ? select.selectedOptions[0] : null;
        const valorBase = opt && opt.dataset.valor ? parseFloat(opt.dataset.valor) : 0;
        if (!valorBase) return;

        const esperancaInput = linha.querySelector('input[name="esperanca_pacientes[]"]');
        const realInput = linha.querySelector('input[name="real_pacientes[]"]');
        const esperanca = esperancaInput && esperancaInput.value ? parseInt(esperancaInput.value, 10) : 0;
        const real = realInput && realInput.value ? parseInt(realInput.value, 10) : 0;

        totalPrevisto += porProcedimento ? valorBase : valorBase * esperanca;
        if (real) {
            totalReal += porProcedimento ? valorBase : valorBase * real;
        }
    });

    previstoEl.textContent = formatarMoeda(totalPrevisto);
    realEl.textContent = formatarMoeda(totalReal);
}

function marcarDiaSemanaPorData(dataStr, force) {
    if (!dataStr) return;
    const data = new Date(dataStr + "T00:00:00");
    if (isNaN(data)) return;
    const diaSemana = (data.getDay() + 6) % 7; // getDay(): 0=Domingo..6=Sábado -> 0=Segunda..6=Domingo
    const radio = document.getElementById(`dia_semana_${diaSemana}`);
    if (radio && (force || !document.querySelector('[name="dia_semana"]:checked'))) {
        radio.checked = true;
    }
}

// Datas (YYYY-MM-DD) da recorrência que seriam excluídas com a data final atual do campo.
function datasRecorrenciaExcluidas() {
    const input = document.getElementById("id_data_final_recorrencia");
    if (!input || !input.value || !input.dataset.datasRecorrencia) return [];
    return input.dataset.datasRecorrencia.split(",").filter((d) => d > input.value);
}

function atualizarAvisoRecorrencia() {
    const aviso = document.getElementById("aviso-encurtar-recorrencia");
    if (!aviso) return;
    const datas = datasRecorrenciaExcluidas();
    aviso.hidden = datas.length === 0;
    if (datas.length) {
        const formatadas = datas.map((d) => d.split("-").reverse().join("/")).join(", ");
        aviso.textContent = `${datas.length} agenda(s) desta recorrência serão excluídas ao salvar: ${formatadas}.`;
    }
}

function initFrequenciaToggle() {
    const detalhes = document.getElementById("recorrencia-detalhes");
    const recorrenteRadio = document.getElementById("freq_recorrente");
    if (!detalhes || !recorrenteRadio) return;
    detalhes.hidden = !recorrenteRadio.checked;

    const dataInicialInput = document.querySelector('[name="data_inicial"]');
    if (dataInicialInput) {
        marcarDiaSemanaPorData(dataInicialInput.value, false);
    }
}

document.addEventListener("click", function (e) {
    const eventoCard = e.target.closest(".abrir-evento");
    if (eventoCard) {
        if (eventoCard.dataset.temMedico === "1") {
            loadListaAgendamentos(eventoCard.dataset.data);
        } else {
            loadCadastroAgenda(eventoCard.dataset.agendaId);
        }
        return;
    }

    const abrirCadastroBtn = e.target.closest(".abrir-cadastro");
    if (abrirCadastroBtn) {
        loadCadastroAgenda(abrirCadastroBtn.dataset.agendaId);
        return;
    }

    const linha = e.target.closest(".linha-agendamento");
    if (linha) {
        loadCadastroAgenda(linha.dataset.agendaId);
        return;
    }

    const addBtn = e.target.closest("#btn-add-procedimento");
    if (addBtn) {
        const tbody = document.getElementById("procedimentos-body");
        const first = tbody.querySelector(".linha-procedimento");
        const clone = first.cloneNode(true);
        clone.querySelectorAll("input").forEach((i) => {
            i.value = i.name === "esperanca_pacientes[]" ? "1" : "";
        });
        clone.querySelectorAll("select").forEach((s) => (s.value = ""));
        tbody.appendChild(clone);
        recalcularValores();
        return;
    }

    const removeBtn = e.target.closest(".btn-remover-linha");
    if (removeBtn) {
        const tbody = document.getElementById("procedimentos-body");
        if (tbody.querySelectorAll(".linha-procedimento").length > 1) {
            removeBtn.closest(".linha-procedimento").remove();
            recalcularValores();
        }
        return;
    }

    const abrirMedicoBtn = e.target.closest(".abrir-medico");
    if (abrirMedicoBtn) {
        loadMedicoForm(abrirMedicoBtn.dataset.medicoId);
        return;
    }

    const excluirMedicoBtn = e.target.closest(".btn-excluir-medico");
    if (excluirMedicoBtn) {
        if (confirm("Excluir este médico? Essa ação não pode ser desfeita.")) {
            document.getElementById(`form-excluir-medico-${excluirMedicoBtn.dataset.medicoId}`).submit();
        }
        return;
    }

    const abrirConciergeBtn = e.target.closest(".abrir-concierge");
    if (abrirConciergeBtn) {
        loadConciergeForm(abrirConciergeBtn.dataset.conciergeId);
        return;
    }

    const excluirConciergeBtn = e.target.closest(".btn-excluir-concierge");
    if (excluirConciergeBtn) {
        if (confirm("Excluir este concierge? Essa ação não pode ser desfeita.")) {
            document.getElementById(`form-excluir-concierge-${excluirConciergeBtn.dataset.conciergeId}`).submit();
        }
        return;
    }
});

document.addEventListener("submit", function (e) {
    if (e.target.querySelector("#id_data_final_recorrencia")) {
        const qtd = datasRecorrenciaExcluidas().length;
        if (qtd && !confirm(`Isso vai excluir ${qtd} agenda(s) posteriores desta recorrência. Essa ação não pode ser desfeita. Continuar?`)) {
            e.preventDefault();
            return;
        }
    }
    if (e.target.matches(".lista-filtros")) {
        e.preventDefault();
        const form = e.target;
        loadListaAgendamentos(form.dataset.dia, {
            q: form.querySelector("[name=q]").value,
            ordenar: form.querySelector("[name=ordenar]").value,
        });
    }
});

document.addEventListener("change", function (e) {
    if (e.target.id === "id_unidade") {
        filtrarPorUnidade(e.target.value);
    }
    if (e.target.name === "frequencia") {
        const detalhes = document.getElementById("recorrencia-detalhes");
        if (detalhes) detalhes.hidden = e.target.value !== "semanal";
    }
    if (e.target.name === "data_inicial") {
        marcarDiaSemanaPorData(e.target.value, true);
    }
    if (e.target.id === "id_medico_inicial") {
        // Refiltra para reexibir, no substituto, o médico inicial anterior.
        filtrarPorUnidade(document.getElementById("id_unidade").value);
    }
    if (e.target.id === "id_medico_substituto" || e.target.name === "medico_inicial_status") {
        atualizarCamposMedico();
    }
    if (e.target.id === "id_data_final_recorrencia") {
        atualizarAvisoRecorrencia();
    }
    if (
        e.target.name === "procedimento[]" ||
        e.target.name === "esperanca_pacientes[]" ||
        e.target.name === "real_pacientes[]" ||
        e.target.name === "tipo_calculo_pagamento"
    ) {
        recalcularValores();
    }
});

document.addEventListener("input", function (e) {
    if (e.target.name === "esperanca_pacientes[]" || e.target.name === "real_pacientes[]") {
        recalcularValores();
    }
});
