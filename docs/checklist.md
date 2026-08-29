# 새 머신에 세우기

```bash
git clone <이 저장소> ~/ai-agent-dotfiles
cd ~/ai-agent-dotfiles && ./install.sh
cp local/ssh-config ~/.ssh/config && chmod 600 ~/.ssh/config   # 있으면
source ~/.bashrc
claude          # 플러그인 자동 설치 + /login
```

## 확인

| 명령 | 봐야 할 것 |
|---|---|
| `./install.sh --check` | 링크가 전부 `ok` |
| `claude-accounts` | 계정별 로그인 · 공유 링크 |
| `claude doctor` | 설치 건강성 |
| `tmux ls` | 창 이름이 `⏳🔵repo` 형태인지 |

## 저장소에 없어서 매번 다시 하는 것

SSH 키 (`ssh-keygen` → `gh ssh-key add`) · gh · Claude · Codex 로그인.
언어/런타임 환경은 프로젝트 소유다.
