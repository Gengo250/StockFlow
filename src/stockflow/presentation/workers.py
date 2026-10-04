"""Executar trabalho lento fora da thread da interface.

POR QUE ISTO EXISTE

A tela de Estoque ganhou um estado "carregando", e ele não aparecia: a
consulta ao catálogo roda na mesma thread que desenha a janela, então entre
`begin_loading()` e `reload_products()` o Qt nunca chega a repintar. O aviso
existia, era testável, e o usuário via a janela congelar — que é o oposto do
feedback que ele deveria dar.

Com três requisições por recarga e latência de rede, congelar não é detalhe:
é a diferença entre "está carregando" e "travou".

O QUE NÃO FAZER COM ISTO

A função chamada roda em OUTRA thread. Ela não pode tocar widget nenhum —
Qt exige que a interface seja manipulada só pela thread principal. Use-a
para I/O puro (consulta, leitura de arquivo) e deixe o desenho para os
callbacks, que o Qt entrega de volta na thread certa por conexão enfileirada.
"""

from PySide6.QtCore import QObject, QThread, Signal, Slot

# Threads, tarefas e entregadores em andamento. Sem esta referência o coletor
# de lixo do Python destrói o `QObject` enquanto o C++ ainda o usa, e o
# processo morre com falha de segmentação — o erro clássico de QThread em
# PySide.
_EM_ANDAMENTO: set = set()


class _Tarefa(QObject):
    """Executa a função na thread secundária e devolve o resultado por sinal.

    Captura QUALQUER exceção de propósito: o que roda aqui é I/O, e uma
    exceção não capturada numa thread secundária não sobe para lugar nenhum
    — ela some, e a tela fica em "carregando" para sempre.
    """

    concluida = Signal(object)
    falhou = Signal(object)

    def __init__(self, funcao):
        super().__init__()
        self._funcao = funcao

    @Slot()
    def executar(self):
        try:
            resultado = self._funcao()
        except Exception as erro:              # noqa: BLE001 - ver docstring
            self.falhou.emit(erro)
        else:
            self.concluida.emit(resultado)
        finally:
            # Encerra o laço DESTA thread, de dentro dela. Conectar
            # `concluida` a `thread.quit` não serve: `thread` tem afinidade
            # com a thread principal, então a chamada seria enfileirada lá —
            # e quem espera com `wait()` bloqueia exatamente essa fila. O
            # resultado é um impasse em que a tarefa termina e a thread
            # nunca encerra.
            QThread.currentThread().quit()


class _Entregador(QObject):
    """Recebe o resultado na thread da INTERFACE e chama o callback.

    Existe porque conectar um sinal direto a uma função Python comum produz
    conexão DIRETA: o callback rodaria na thread secundária, e tocar widget
    de lá é exatamente o que o Qt proíbe. Um `QObject` criado na thread
    principal força a conexão a ser enfileirada e devolve a execução para
    onde desenhar é legal.
    """

    def __init__(self, ao_concluir, ao_falhar):
        super().__init__()
        self._ao_concluir = ao_concluir
        self._ao_falhar = ao_falhar
        self._registro = None

    def registrar(self, registro):
        self._registro = registro

    @Slot(object)
    def concluir(self, resultado):
        try:
            self._ao_concluir(resultado)
        finally:
            self._liberar()

    @Slot(object)
    def falhar(self, erro):
        try:
            self._ao_falhar(erro)
        finally:
            self._liberar()

    def _liberar(self):
        """Solta a referência DEPOIS de entregar, nunca antes.

        Soltar no `finished` da thread seria cedo: a entrega é uma chamada
        enfileirada na thread da interface, e ela pode estar na fila quando
        a thread já terminou. Sem nenhuma referência viva nesse intervalo, o
        entregador é coletado e a entrega nunca acontece — uma recarga que
        some sem erro nenhum.
        """
        _EM_ANDAMENTO.discard(self._registro)
        self._registro = None


def executar_em_segundo_plano(funcao, ao_concluir, ao_falhar):
    """Roda `funcao` noutra thread e chama um dos callbacks na thread da UI.

    Devolve a `QThread` para quem precisar esperar (os testes esperam). Os
    callbacks são conectados antes de `start()`: uma função rápida poderia
    terminar antes de alguém estar ouvindo.
    """
    thread = QThread()
    tarefa = _Tarefa(funcao)
    entregador = _Entregador(ao_concluir, ao_falhar)   # fica na thread atual
    tarefa.moveToThread(thread)

    thread.started.connect(tarefa.executar)
    tarefa.concluida.connect(entregador.concluir)
    tarefa.falhou.connect(entregador.falhar)

    registro = (thread, tarefa, entregador)
    _EM_ANDAMENTO.add(registro)
    entregador.registrar(registro)

    # Sem `deleteLater` aqui, de propósito. Na thread: quem chama recebe a
    # `QThread` de volta e pode esperá-la, e agendar a destruição faria a
    # referência dele apontar para um objeto C++ já apagado. Na tarefa: ela
    # vive na thread secundária, cujo laço de eventos já encerrou — um
    # `deleteLater` ali nunca seria processado. As duas são liberadas pelo
    # coletor do Python quando o registro sai de `_EM_ANDAMENTO`.

    thread.start()
    return thread


def executar_agora(funcao, ao_concluir, ao_falhar):
    """Mesma assinatura, sem thread. Para teste e para o modo demonstração.

    Um teste de UI não tem laço de eventos girando, então uma tarefa em
    segundo plano nunca entregaria o resultado e o teste esperaria para
    sempre. E no modo demonstração não há I/O: trocar de thread para ler um
    dict em memória só adiciona caminhos para errar.
    """
    try:
        resultado = funcao()
    except Exception as erro:                  # noqa: BLE001
        ao_falhar(erro)
    else:
        ao_concluir(resultado)
    return None
