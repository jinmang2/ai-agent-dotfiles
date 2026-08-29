# 새 머신에 세우기

```bash
gh auth login                                  # 1. 먼저. local/ 서브모듈이 이걸 탄다
git clone --recursive https://github.com/jinmang2/ai-agent-dotfiles ~/ai-agent-dotfiles
cd ~/ai-agent-dotfiles && ./install.sh          # 2. 설정 배치
cp local/ssh-config ~/.ssh/config && chmod 600 ~/.ssh/config
source ~/.bashrc
claude                                          # 3. 플러그인 자동 설치 + /login
```

서브모듈 URL 은 HTTPS 다. 예전엔 SSH 였는데, SSH 키 등록이 이 순서에서 clone 보다
뒤라 서로를 기다리는 교착이 있었다. HTTPS 는 `gh auth git-credential` 로
비공개 저장소도 clone·push 가 되므로 `gh auth login` 하나만 먼저 하면 된다.

`--recursive` 를 빠뜨렸으면 `git submodule update --init`. 서브모듈이 비어 있어도
`install.sh` 는 정상 동작한다 — 머신 고유 오버레이와 `ssh-config` 만 빠진다.

## 확인

| 명령 | 봐야 할 것 |
|---|---|
| `./install.sh --check` | 링크가 전부 `ok` |
| `claude-accounts` | 계정별 로그인 · 공유 링크가 `정상` |
| `claude doctor` | 설치 건강성 |
| `tmux ls` | 창 이름이 `⏳🔵repo` 형태인지 |

창 이름이 안 붙으면 tmux 밖이거나 `automatic-rename` 이 켜져 있는 것이다.
훅 자체는 이렇게 직접 찔러본다:

```bash
printf '{"cwd":"%s"}' "$PWD" | agent-window-label ⏳ probe && tmux display -p '#{window_name}'
```

## git 신원

저장소에 두지 않는다. `~/.gitconfig` 는 `gh auth` 와 `git config --global` 이 수시로
다시 쓰기 때문에 심링크로 걸면 끊긴다.

```bash
git config --global user.name  "<이름>"
git config --global user.email "<이메일>"
```

## 저장소에 없어서 매번 다시 하는 것

SSH 키 (`ssh-keygen` → `gh ssh-key add`) · gh · Claude · Codex 로그인.
언어/런타임 환경(conda·nvm·CUDA)은 프로젝트 소유다.

프레임워크는 재설치로 복원한다 — 저장소에 담지 않는다:

```bash
npm i -g @openai/codex oh-my-codex && omx setup                            # Codex + OMX
git clone https://github.com/garrytan/gstack.git ~/.claude/skills/gstack   # 선택 (1.5G)
```

`~/.claude/CLAUDE.md` 도 여기 속한다. OMC 가 소유하고 `omc setup` 이 덮어쓰므로
(`<!-- OMC:VERSION:... -->` 표시가 있다) 심링크로 걸면 `~/.gitconfig` 와 같은 이유로
끊긴다. 개인 지침을 넣었다면 `omc setup` 뒤에 다시 넣어야 한다.
