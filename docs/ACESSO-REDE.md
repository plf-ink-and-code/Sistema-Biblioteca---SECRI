# Acesso pela rede (LAN) — incluindo WSL2

Como abrir o app de **outro PC na mesma rede**. O servidor já escuta em todas as
interfaces (`ui.run(host="0.0.0.0", ...)` em `src/main.py`) e o compose publica a
porta (`8080:8080`), então do lado da aplicação não falta nada — o resto é rede.

---

## Conceito básico: `localhost` nunca funciona de outro PC

`localhost` (e `127.0.0.1`) **sempre** significa "a própria máquina". De outro
computador, `localhost:8080` aponta para ele mesmo, não para o servidor.

De outro PC use sempre o **IP da máquina que roda o container**, por exemplo:

```
http://192.168.18.2:8080
```

Para descobrir o IP da máquina servidora (Linux nativo):

```bash
ip -4 addr show scope global | awk '/inet/ {print $2}'
```

Use o IP da faixa da sua LAN (tipicamente `192.168.x.x` ou `10.x.x.x`). Ignore os
IPs `172.x` — são das redes internas do Docker.

---

## Linux nativo (não WSL)

Normalmente funciona direto. Se não abrir de outro PC:

1. **Firewall da máquina** — causa mais comum:
   ```bash
   sudo ufw allow 8080/tcp          # Ubuntu/Debian (ufw)
   sudo firewall-cmd --add-port=8080/tcp   # Fedora/RHEL (firewalld)
   ```
2. **Mesma rede** — confirme que ambos estão no mesmo Wi-Fi/roteador e que não há
   "isolamento de cliente" (comum em redes de convidado).
3. **Teste rápido** do outro PC: `http://<IP-do-servidor>:8080/health` deve
   retornar `{"status":"ok"}`.

---

## WSL2 (importante — comportamento diferente)

Quando a máquina servidora roda em **WSL2**, o acesso pela LAN **não funciona por
padrão**. O WSL2 roda numa VM com rede virtual isolada (NAT) e IP próprio
(`172.x`), diferente do IP do Windows na rede.

```
Outro PC na LAN ──► IP do Windows (192.168.x.x) ──✗──► container:8080 (dentro do WSL2)
                                                  │
                              o Windows NÃO encaminha a porta pro WSL2 sozinho
```

- Do **próprio Windows** que hospeda o WSL, `localhost:8080` funciona (a Microsoft
  faz um relay automático de localhost).
- De **outro PC**, `http://<IP-do-Windows>:8080` **não** chega no container sem
  uma das configurações abaixo.

### Solução recomendada: modo de rede `mirrored`

Faz o WSL2 compartilhar a interface de rede do Windows — o IP do Windows na LAN
passa a valer também para o WSL. Requer **Windows 11 + WSL recente**
(verifique com `wsl --version`).

No **Windows**, crie/edite o arquivo `C:\Users\<seu-usuario>\.wslconfig`:

```ini
[wsl2]
networkingMode=mirrored
```

Depois, no **PowerShell**:

```powershell
wsl --shutdown
```

Reabra o WSL. Agora `http://<IP-do-Windows>:8080` funciona de outro PC. Este modo
também dá **IP estável** (não muda a cada reboot).

### Alternativa (Windows 10 / WSL antigo): portproxy

Encaminha a porta do Windows para dentro do WSL manualmente.

1. Descubra o IP do WSL (**dentro do WSL**):
   ```bash
   hostname -I
   ```
2. No **PowerShell como Administrador** (no Windows):
   ```powershell
   netsh interface portproxy add v4tov4 `
     listenaddress=0.0.0.0 listenport=8080 `
     connectaddress=<IP-DO-WSL> connectport=8080

   netsh advfirewall firewall add rule name="WSL Biblioteca 8080" `
     dir=in action=allow protocol=TCP localport=8080
   ```

> ⚠️ No modo NAT, o **IP do WSL2 muda a cada reboot**, então esse `portproxy`
> quebra após reiniciar e precisa ser refeito. Por isso o modo `mirrored` é bem
> melhor para algo que fica sempre ligado.
>
> Para remover o portproxy depois:
> ```powershell
> netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=8080
> ```

### Docker Desktop com integração WSL

Se você usa Docker Desktop (integração WSL ativada), a porta publicada já aparece
no `localhost` do Windows automaticamente. Para o acesso pela LAN, ainda vale o
modo `mirrored` (ou o portproxy) — mais o firewall do Windows liberado.

---

## Checklist WSL2 (ordem de importância)

1. **`networkingMode=mirrored`** no `.wslconfig` (resolve rede + IP estável).
2. **Firewall do Windows** liberando a porta 8080 (o bloqueio é do Windows, não do
   Linux de dentro do WSL).
3. **Roteador**: mesmos PCs na mesma rede, sem isolamento de cliente.
4. Container com `restart: always` (já configurado no `docker-compose.yml`) e
   Docker iniciando junto com a distro/boot.

---

## Segurança ao expor na LAN

Ao publicar na rede, qualquer dispositivo dela alcança o app. O login protege o
acesso, mas hoje é **HTTP puro (sem TLS)** — usuário e senha trafegam em claro na
rede local. Para uso interno de teste tudo bem; para uso "de verdade":

- Troque `ADMIN_PASSWORD` e defina `AUTH_SECRET` (ver `README.md` → Autenticação).
- Considere um proxy reverso com HTTPS na frente (ex.: Caddy/nginx) se o acesso
  sair da LAN de confiança.
