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

function filtrarPorUnidade(unidadeId) {
    document.querySelectorAll("#id_sala option[data-unidade]").forEach((opt) => {
        opt.hidden = !(!unidadeId || opt.dataset.unidade === unidadeId);
    });
    const salaSelect = document.getElementById("id_sala");
    if (salaSelect && salaSelect.selectedOptions[0] && salaSelect.selectedOptions[0].hidden) {
        salaSelect.value = "";
    }
    document.querySelectorAll('select[name="procedimento[]"]').forEach((sel) => {
        sel.querySelectorAll("option[data-unidade]").forEach((opt) => {
            opt.hidden = !(!unidadeId || opt.dataset.unidade === unidadeId);
        });
    });
}

function initCadastroForm() {
    const unidadeSelect = document.getElementById("id_unidade");
    if (unidadeSelect) {
        filtrarPorUnidade(unidadeSelect.value);
    }
    initFrequenciaToggle();
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
});

document.addEventListener("submit", function (e) {
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
