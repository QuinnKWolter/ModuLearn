"""Read-only HTTP/DNS checks; run inside the production container via stdin.

Optional positional arguments are candidate IPv4 addresses, not assumed gateways.
No learner credentials, answers or session identifiers are sent.
"""
import http.client
import ipaddress
import socket
import sys


def main():
    candidates = [str(ipaddress.IPv4Address(value)) for value in sys.argv[1:]]
    for host in ('pawscomp2.sis.pitt.edu', 'adapt2.sis.pitt.edu'):
        try:
            resolved = list(dict.fromkeys(info[4][0] for info in socket.getaddrinfo(
                host, 80, family=socket.AF_INET, type=socket.SOCK_STREAM)))
        except OSError as error:
            resolved = []
            print(f'{host}: resolution failed: {error}', flush=True)
        print(f'{host}: current IPv4 = {resolved}', flush=True)
        for address in dict.fromkeys(resolved + candidates):
            connection = http.client.HTTPConnection(address, 80, timeout=5)
            try:
                connection.request('GET', '/quizjet/displayQuiz.jsp?rdfID=jSimpleVariableTest',
                                   headers={'Host': host, 'User-Agent': 'ModuLearn-network-check/1.0'})
                response = connection.getresponse()
                body = response.read(65536).decode('utf-8', errors='replace').lower()
                activity = 'evaluateanswer' in body or 'quizjet' in body
                print(f'  {address}: HTTP {response.status}; QuizJET markers={activity}', flush=True)
            except (OSError, http.client.HTTPException) as error:
                print(f'  {address}: {type(error).__name__}: {error}', flush=True)
            finally:
                connection.close()


if __name__ == '__main__':
    main()
