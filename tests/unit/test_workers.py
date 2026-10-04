"""Trabalho lento sai da thread da interface e volta por sinal.

O estado "carregando" da tela de Estoque existia, era testável, e nunca
aparecia: a consulta rodava na mesma thread que desenha a janela, então o Qt
não chegava a repintar entre o aviso e o resultado. O usuário via a janela
congelar — o oposto do feedback que o aviso deveria dar.
"""

import threading

from PySide6.QtCore import QThread

from stockflow.presentation.workers import executar_agora, executar_em_segundo_plano


def esperar(thread, qapp, limite_ms=5000):
    """Espera a tarefa terminar E os sinais chegarem na thread da UI."""
    assert thread.wait(limite_ms), "a tarefa não terminou no tempo"
    qapp.processEvents()


def test_a_funcao_roda_em_OUTRA_thread(qapp):
    """O ponto todo do módulo. Se rodar na mesma, a janela congela."""
    principal = threading.get_ident()
    onde = {}

    esperar(executar_em_segundo_plano(
        lambda: onde.setdefault("tarefa", threading.get_ident()),
        lambda _r: None, lambda _e: None,
    ), qapp)

    assert onde["tarefa"] != principal


def test_o_resultado_volta_pelo_callback(qapp):
    recebidos = []
    esperar(executar_em_segundo_plano(
        lambda: {"catalogo": 42}, recebidos.append, lambda _e: None,
    ), qapp)

    assert recebidos == [{"catalogo": 42}]


def test_excecao_vira_callback_de_falha(qapp):
    """Exceção numa thread secundária não sobe para lugar nenhum.

    Sem capturá-la, ela simplesmente some — e a tela fica em "carregando"
    para sempre, que é pior do que mostrar o erro.
    """
    erros = []

    def explodir():
        raise RuntimeError("timeout na consulta")

    esperar(executar_em_segundo_plano(
        explodir, lambda _r: None, erros.append,
    ), qapp)

    assert len(erros) == 1
    assert isinstance(erros[0], RuntimeError)
    assert "timeout na consulta" in str(erros[0])


def test_a_thread_encerra_sozinha(qapp):
    """Thread que não encerra impede o processo de fechar."""
    thread = executar_em_segundo_plano(lambda: None, lambda _r: None, lambda _e: None)
    esperar(thread, qapp)
    assert thread.isFinished()


def test_tarefas_simultaneas_nao_se_atropelam(qapp):
    recebidos = []
    threads = [
        executar_em_segundo_plano(lambda n=n: n, recebidos.append, lambda _e: None)
        for n in range(5)
    ]
    for thread in threads:
        esperar(thread, qapp)

    assert sorted(recebidos) == [0, 1, 2, 3, 4]


# ------------------------------------------------------- versão síncrona


def test_executar_agora_roda_na_thread_atual(qapp):
    """Modo demonstração não tem I/O; trocar de thread só adiciona risco."""
    atual = threading.get_ident()
    onde = {}

    retorno = executar_agora(
        lambda: onde.setdefault("tarefa", threading.get_ident()),
        lambda _r: None, lambda _e: None,
    )

    assert onde["tarefa"] == atual
    assert retorno is None, "sem thread para esperar"


def test_executar_agora_tambem_captura_a_falha(qapp):
    """As duas versões precisam ter o mesmo contrato de erro."""
    erros = []

    def explodir():
        raise ValueError("falhou")

    executar_agora(explodir, lambda _r: None, erros.append)
    assert isinstance(erros[0], ValueError)
