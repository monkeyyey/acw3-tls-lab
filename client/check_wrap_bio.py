
import ssl
import sys

print("Python version:", sys.version.split()[0])

context = ssl.create_default_context()

print("Hostname checking:", context.check_hostname)

incoming = ssl.MemoryBIO()
outgoing = ssl.MemoryBIO()

try:
    context.wrap_bio(
        incoming,
        outgoing,
        server_side=False,
        server_hostname=None
    )
    print("RESULT: Missing hostname accepted")

except ValueError as error:
    print("RESULT: Missing hostname rejected")
    print(error)
