"""Spawn-based solver adapter. Pygame is never imported by a worker."""
from __future__ import annotations
import multiprocessing as mp
from time import monotonic
from src.engine.problem import BloxorzProblem
from src.engine.state import Action
from src.gui.contracts import SolverRequest, SolverResponse, SolverResultView, SolverMetrics, SolverStatus


def _solve(request, connection):
    try:
        from src.solvers.uninformed import BFS, DFS, UCS
        from src.solvers.astar import AStar
        solver = {'BFS': BFS, 'IDS': DFS, 'UCS': UCS, 'ASTAR': AStar}[request.algorithm]()
        result = solver.solve(BloxorzProblem(request.stage, request.initial_state))
        view = SolverResultView(request.algorithm, result.found,
            tuple(Action(a) for a in result.path),
            SolverMetrics(result.time_sec, result.peak_memory_mb, result.expanded_nodes,
                          result.solution_length, result.total_cost))
        connection.send(SolverResponse(request.request_id,
            SolverStatus.SOLVED if result.found else SolverStatus.NO_SOLUTION, view))
    except Exception as error:
        connection.send(SolverResponse(request.request_id, SolverStatus.ERROR,
            SolverResultView(request.algorithm, False, error=str(error))))
    finally:
        connection.close()


class ProcessSolverGateway:
    def __init__(self):
        self.process = None
        self.connection = None
        self.request = None
        self.started = 0.0
        self.pending = None
        self.retired = []

    @property
    def busy(self):
        return self.request is not None

    def submit(self, request: SolverRequest):
        if self.busy:
            raise RuntimeError('Solver is busy.')
        if request.timeout_sec <= 0:
            raise ValueError('Timeout must be positive.')
        context = mp.get_context('spawn')
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=_solve, args=(request, sender), daemon=True)
        try:
            process.start()
        except Exception:
            receiver.close()
            sender.close()
            raise
        sender.close()
        self.process, self.connection = process, receiver
        self.request, self.started = request, monotonic()

    def _finish(self, status=None):
        request = self.request
        if status is not None:
            self.pending = SolverResponse(request.request_id, status,
                SolverResultView(request.algorithm, False, error=status.value))
        if self.process.is_alive():
            self.process.terminate()
        self.retired.append(self.process)
        self.connection.close()
        self.process = self.connection = self.request = None

    def poll(self):
        for process in self.retired[:]:
            if not process.is_alive():
                process.join()
                process.close()
                self.retired.remove(process)
        if self.pending is not None:
            response, self.pending = self.pending, None
            return response
        if not self.busy:
            return None
        if self.connection.poll():
            try:
                response = self.connection.recv()
            except (EOFError, OSError):
                self._finish(SolverStatus.ERROR)
                return self.poll()
            self._finish()
            return response
        if monotonic() - self.started >= self.request.timeout_sec:
            self._finish(SolverStatus.TIMEOUT)
        elif not self.process.is_alive():
            self._finish(SolverStatus.ERROR)
        if self.pending is not None:
            response, self.pending = self.pending, None
            return response
        return None

    def cancel(self, request_id):
        if self.busy and self.request.request_id == request_id:
            self._finish(SolverStatus.CANCELLED)

    def close(self):
        if self.busy:
            self._finish()
        for process in self.retired:
            process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
            process.close()
        self.retired.clear()
        self.pending = None
