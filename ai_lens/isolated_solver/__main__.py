"""Single JSON request from stdin, JSON response on stdout."""
import sys
from .client import solve
from .protocol import MAX_INPUT, MAX_OUTPUT, SolverError, loads, dumps, response

def main():
    try:
        value=loads(sys.stdin.buffer.read(MAX_INPUT+1))
        answer=solve(value)
    except SolverError as exc:
        answer=response(None,exc.status,error=str(exc))
    sys.stdout.buffer.write(dumps(answer,MAX_OUTPUT)+b'\n')

if __name__=='__main__':
    main()
