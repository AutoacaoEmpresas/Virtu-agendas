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
        return;
    }

    const removeBtn = e.target.closest(".btn-remover-linha");
    if (removeBtn) {
        const tbody = document.getElementById("procedimentos-body");
        if (tbody.querySelectorAll(".linha-procedimento").length > 1) {
            removeBtn.closest(".linha-procedimento").remove();
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
});
