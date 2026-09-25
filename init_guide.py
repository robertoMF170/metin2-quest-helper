# init_guide.py -- MT2Guide (Quest Helper puro, estilo RestedXP)
# -*- coding: utf-8 -*-
# O eXLib corre este ficheiro DUAS vezes:
#   chamada 1 (injecao, PythonModule.cpp) -> metade BOOTSTRAP;
#   chamada 2 (App.cpp, primeiro in-game) -> metade LOADER.
# Este init NAO carrega bots: so' o quest helper (seta, passos, dialogos).
# Para voltar aos bots: trocar por o init.py do MT2Robs.
#
# Comandos no chat:  .g      -> abre/fecha o guia
#                    .q      -> abre/fecha a quest line (seletor de missoes)
#                    .qdiag  -> diagnostico do passo atual p/ syserr_guide.txt
#                    .qkey   -> trace de TODAS as teclas durante 60s (debug)
#                    .qpos   -> grava a posicao atual em MT2Guide\Data\posicoes.txt
#                    .qstate -> estado REAL das quests da conta/personagem
#                               (feitas / a meio / contadores) no log
#                    .qdump  -> dump das APIs (quest/event/eXLib) para api_dump.txt
#                               + MT2Guide\Data\api_dump_quest.txt (o modulo das
#                               quests do cliente, usado pela sincronizacao)
# Teclas:            INSERT ou F7 -> abre/fecha o menu do guia
#                    N ou F8      -> abre/fecha a quest line (todas as missoes;
#                                   a janela de missoes do jogo fica suprimida)
import sys
if not getattr(sys, '_mt2guide_phase2', False):
    sys._mt2guide_phase2 = True
    # ===================== BOOTSTRAP =====================
    import ui, sys, os
    import eXLib
    import chr, app
    _chr = chr

    # descobrir os nomes reais dos modulos do cliente (podem ter prefixo)
    b = sys.modules.keys()
    playerm = None
    netm = None
    chatm = None
    for i in range(len(b)):
        h = b[i]
        if '.' in h:
            continue
        try:
            a = dir(__import__(b[i]))
        except:
            continue
        for y in range(len(a)):
            if a[y] == 'GetMainCharacterIndex':
                playerm = b[i]
            if a[y] == 'SendChatPacket':
                netm = b[i]
            if a[y] == 'AppendChat':
                chatm = b[i]

    _player = None
    _net = None
    _chat = None
    if playerm:
        _player = __import__(playerm)
    if netm:
        _net = __import__(netm)
    if chatm:
        _chat = __import__(chatm)

    if _player is not None:
        sys.modules['player'] = _player
    if _net is not None:
        sys.modules['net'] = _net
    if _chat is not None:
        sys.modules['chat'] = _chat

    # ---- ponte de teclas EXATA do original (passthrough) ----
    # O C++ do eXLib chama AMBAS; se faltar alguma, a pipeline de teclas
    # rebenta (M/I/N/... morrem).
    _g_kl_last = {}

    def _g_keylog(name):
        # diagnostico: confirma que a tecla chega ao hook do guia
        try:
            import time as _t
            now = _t.time()
            if now - _g_kl_last.get(name, 0.0) < 2.0:
                return
            _g_kl_last[name] = now
            f = open(eXLib.PATH + 'syserr_guide.txt', 'a')
            f.write('[tecla] %s chegou ao hook do guia\n' % name)
            f.close()
        except:
            pass

    def _g_keytrace(key, state):
        # .qkey: durante 60s escreve TODAS as teclas que chegam ao hook
        try:
            import time as _t
            until = getattr(sys, '_mt2guide_keytrace_until', 0.0)
            if state != 1 or _t.time() > until:
                return
            f = open(eXLib.PATH + 'syserr_guide.txt', 'a')
            f.write('[keytrace] tecla=%s (DIK %s)\n' % (key, key))
            f.close()
        except:
            pass

    def SetSingleDIKKeyState(key, state):
        try:
            _g_keytrace(key, state)
            # modo pesquisa do guia (quest line aberta): as teclas de
            # texto alimentam a pesquisa (SEM IME, sem caixa de texto)
            if state == 1:
                try:
                    sk = getattr(sys, '_mt2guide_searchkey', None)
                    if sk is not None and sk(key):
                        return
                except:
                    pass
            # INSERT ou F7 -> abrir/fechar o menu do guia
            # (F7 e' alternativa se o INSERT estiver morto/ime)
            if state == 1 and key in (getattr(app, 'DIK_INSERT', 210),
                                      getattr(app, 'DIK_F7', 65)):
                try:
                    tg = getattr(sys, '_mt2guide_toggle', None)
                    if tg is not None:
                        _g_keylog('INSERT/F7' if key == 210 else 'F7')
                        tg()
                        return
                except:
                    pass
            # N ou F8 -> abre/fecha a QUEST LINE do guia (todas as missoes).
            # A tecla NAO chega ao jogo: a janela de missoes original
            # fica suprimida (deixava de ficar por cima do guia).
            if state == 1 and key in (getattr(app, 'DIK_N', 49),
                                      getattr(app, 'DIK_F8', 66)):
                try:
                    nt = getattr(sys, '_mt2guide_ntoggle', None)
                    if nt is not None:
                        _g_keylog('N/F8')
                        nt()
                        return
                except:
                    pass
        except:
            pass
        try:
            if state == 1:
                _player.OnKeyDown(key)
            else:
                _player.OnKeyUp(key)
        except:
            pass

    def SetAttackKeyState(state):
        try:
            if state == 1:
                _player.OnKeyDown(app.DIK_SPACE)
            else:
                _player.OnKeyUp(app.DIK_SPACE)
        except:
            pass

    try:
        setattr(chr, 'GetPixelPosition', eXLib.GetPixelPosition)
        setattr(chr, 'MoveToDestPosition', eXLib.MoveToDestPosition)
        if _player is not None:
            setattr(_player, 'SetSingleDIKKeyState', SetSingleDIKKeyState)
            setattr(_player, 'SetAttackKeyState', SetAttackKeyState)
    except:
        pass

    # ---- paths do MT2Guide ----
    sys.path.append(os.path.join(eXLib.PATH))
    sys.path.append(os.path.join(eXLib.PATH, 'MT2Guide'))
    sys.path.append(os.path.join(eXLib.PATH, 'MT2Guide', 'Modules'))

else:
    # ===================== LOADER (primeiro in-game) =====================
    import sys
    import __builtin__ as buildin
    import eXLib
    import os

    def _g_log(text):
        try:
            from datetime import datetime
            stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f = open(eXLib.PATH + 'syserr_guide.txt', 'a')
            f.write('[%s] %s\n' % (stamp, text))
            f.close()
        except:
            pass

    _g_log('[MT2Guide] loader start')

    def HasArguments(module, attrlist):
        for attr in attrlist:
            if not buildin.hasattr(module, attr):
                return False
        return True

    for modulename, module in iter(sys.modules.items()):
        if HasArguments(module, ['GetPlayTime']): player = module
        if HasArguments(module, ['GetNameByVID']): chr = module
        if HasArguments(module, ['DirectEnter']): net = module
        if HasArguments(module, ['SetCameraMaxDistance']): app = module
        if HasArguments(module, ['ScriptWindow']): ui = module

    # ---- carregar o guia ----
    GuideUI = None
    try:
        from MT2Guide.Modules import GuideLib
        GuideLib.InstallPhaseHook()
        from MT2Guide.Modules import GuideUI as _GUI
        GuideUI = _GUI
        sys._mt2guide_toggle = GuideUI.switch_state
        sys._mt2guide_ntoggle = GuideUI.toggle_picker
        sys._mt2guide_searchkey = GuideUI.search_key
        _g_log('[MT2Guide] guia carregado')
    except Exception as e:
        _g_log('[MT2Guide] ERRO ao carregar: %r' % e)

    # ---- comandos de chat (.g / .qpos / .qdump) ----
    try:
        if not getattr(net, '_mt2guide_chathook', False):
            net._mt2guide_chathook = True
            _g_orig_chat = net.SendChatPacket

            def _g_chat(*args, **kw):
                try:
                    for a in args:
                        if not buildin.isinstance(a, (str, unicode)):
                            continue
                        t = a.strip().lower()
                        if t == '.g':
                            if GuideUI is not None:
                                GuideUI.switch_state()
                            _g_esc()
                            return
                        if t.startswith('.qp') or t.startswith('.q '):
                            # .qp <texto> -> PESQUISA direta (escrita no chat
                            # do jogo: funciona mesmo que as teclas nao
                            # cheguem ao hook do guia)
                            txt = ''
                            try:
                                raw = a.strip()
                                if raw.lower().startswith('.qp'):
                                    txt = raw[3:].strip()
                                else:
                                    txt = raw[2:].strip()
                            except:
                                pass
                            if GuideUI is not None:
                                try:
                                    if txt:
                                        GuideUI.set_search_text(txt)
                                    else:
                                        GuideUI.arm_search()
                                except Exception as e:
                                    _g_log('[MT2Guide] qp ERR: %r' % e)
                            _g_esc()
                            return
                        if t == '.q':
                            if GuideUI is not None:
                                GuideUI.toggle_picker()
                            _g_esc()
                            return
                        if t == '.qdiag':
                            if GuideUI is not None:
                                GuideUI.dump_diag()
                                _g_log('[MT2Guide] diagnostico escrito')
                            _g_esc()
                            return
                        if t == '.qkey':
                            # trace de teclas durante 60s (debug INSERT/N)
                            try:
                                import time as _t
                                sys._mt2guide_keytrace_until = _t.time() + 60.0
                                _g_log('[MT2Guide] KEYTRACE ativo 60s - carrega nas teclas!')
                            except:
                                pass
                            _g_esc()
                            return
                        if t == '.qpos':
                            _g_writepos()
                            _g_esc()
                            return
                        if t == '.qstate':
                            if GuideUI is not None:
                                try:
                                    GuideUI.instance.OnDumpState()
                                except Exception as e:
                                    _g_log('[MT2Guide] qstate ERR: %r' % e)
                                _g_log('[MT2Guide] estado do jogo escrito')
                            _g_esc()
                            return
                        if t == '.qdump':
                            _g_dump()
                            _g_esc()
                            return
                except:
                    pass
                return _g_orig_chat(*args, **kw)

            net.SendChatPacket = _g_chat
    except Exception as e:
        _g_log('[MT2Guide] chat hook ERR: %r' % e)

    def _g_esc():
        # fechar a caixa de chat depois de engolir o comando (o fix do
        # MT2Robs: sem isto o M/N/I seguinte escrevia no chat)
        try:
            player.OnKeyDown(1)
            player.OnKeyUp(1)
        except:
            pass

    def _g_writepos():
        try:
            from MT2Guide.Modules import GuideLib
            mx, my, mz = GuideLib.GetMyPosition()
            name = GuideLib.GetMyName()
            p = os.path.join(eXLib.PATH, 'MT2Guide', 'Data', 'posicoes.txt')
            f = open(p, 'a')
            f.write('%s | %s | %.0f,%.0f\n' % (GuideLib.GetMapName(), name, mx, my))
            f.close()
            _g_log('[MT2Guide] pos gravada %.0f,%.0f' % (mx, my))
        except Exception as e:
            _g_log('[MT2Guide] qpos ERR: %r' % e)

    def _g_dump():
        # dump das APIs uteis (como o .dump do MT2Robs, mas incluindo quest
        # e event) -> MT2Guide\Data\api_dump.txt
        try:
            out = []
            for name in ('eXLib', 'background', 'chr', 'player', 'app', 'net', 'event'):
                m = sys.modules.get(name)
                if m is None:
                    m = globals().get(name)
                if m is not None:
                    out.append('=== %s ===\n%s' % (name, ', '.join(sorted(dir(m)))))
            # modulo quest: procurar por GetQuestCount
            for mn, mod in iter(sys.modules.items()):
                try:
                    if mod is not None and buildin.hasattr(mod, 'GetQuestCount'):
                        out.append('=== QUEST MOD (%s) ===\n%s' % (mn, ', '.join(sorted(dir(mod)))))
                        break
                except:
                    pass
            p = os.path.join(eXLib.PATH, 'MT2Guide', 'Data', 'api_dump.txt')
            f = open(p, 'w')
            f.write('\n\n'.join(out))
            f.close()
            # diagnostico do guia + DUMP do modulo de quests do cliente
            # (api_dump_quest.txt) + estado REAL (Data/quest_state.txt)
            try:
                if GuideUI is not None:
                    GuideUI.dump_diag()
                    GuideUI.instance.OnDumpState()
            except Exception as e:
                _g_log('[MT2Guide] dump sync ERR: %r' % e)
            _g_log('[MT2Guide] api_dump.txt escrito')
        except Exception as e:
            _g_log('[MT2Guide] dump ERR: %r' % e)

    # ---- reinstalar a ponte de TECLAS (fase 2: o mundo ja existe) ----
    # O cliente pode substituir o modulo player entre a injecao e o jogo,
    # levando com ela o nosso hook (INSERT/N mortos). Reinstalamos aqui
    # em cima do modulo player VERDADEIRO e logamos o estado anterior.
    try:
        _pl = player
        try:
            _cur = getattr(_pl, 'SetSingleDIKKeyState', None)
            _g_log('[keys] antes da fase2: %s' % type(_cur).__name__)
        except:
            _g_log('[keys] antes da fase2: (sem attr)')

        def _g_key2(key, state):
            try:
                if state == 1:
                    try:
                        _kt = getattr(sys, '_mt2guide_keytrace_until', 0.0)
                        import time as _t2
                        if _t2.time() <= _kt:
                            f = open(eXLib.PATH + 'syserr_guide.txt', 'a')
                            f.write('[keytrace] tecla=%s\n' % key)
                            f.close()
                    except:
                        pass
                    try:
                        sk = getattr(sys, '_mt2guide_searchkey', None)
                        if sk is not None and sk(key):
                            return
                    except:
                        pass
                    _app2 = app
                    if key in (getattr(_app2, 'DIK_INSERT', 210), getattr(_app2, 'DIK_F7', 65)):
                        tg = getattr(sys, '_mt2guide_toggle', None)
                        if tg is not None:
                            tg()
                            return
                    if key in (getattr(_app2, 'DIK_N', 49), getattr(_app2, 'DIK_F8', 66)):
                        nt = getattr(sys, '_mt2guide_ntoggle', None)
                        if nt is not None:
                            nt()
                            return
            except:
                pass
            try:
                if state == 1:
                    _pl.OnKeyDown(key)
                else:
                    _pl.OnKeyUp(key)
            except:
                pass

        setattr(_pl, 'SetSingleDIKKeyState', _g_key2)
        _g_log('[keys] ponte de teclas REINSTALADA (fase 2)')
    except Exception as e:
        _g_log('[keys] reinstall ERR: %r' % e)

    # ---- ponte de teclas v2: player.OnKeyDown (METODO COMPROVADO) ----
    # Os logs comprovaram que o wrap do SetSingleDIKKeyState nunca
    # recebe teclas neste cliente (keytrace 60s vazio). O MT2Robs usa
    # player.OnKeyDown para o INSERT e funciona (logs do bot). Fazemos
    # o mesmo: envolvemos OnKeyDown, com re-instalacao periodica (o
    # cliente pode substituir a funcao em reloads do mundo).
    _g_kw_ref = [None]
    _g_kw_last = {}

    def _g_kw_log(name):
        # diagnostico: confirma que a tecla chegou (throttle 2s)
        try:
            import time as _t
            now = _t.time()
            if now - _g_kw_last.get(name, 0.0) < 2.0:
                return
            _g_kw_last[name] = now
            _g_log('[tecla] %s chegou (OnKeyDown)' % name)
        except:
            pass

    def _g_install_kwrap():
        try:
            cur = getattr(player, 'OnKeyDown', None)
            if cur is None:
                _g_log('[keys] player.OnKeyDown nao existe')
                return
            if _g_kw_ref[0] is not None and cur is _g_kw_ref[0]:
                return   # ja' instalada
            def _g_onkey(key, _orig=cur):
                try:
                    # .qkey: trace de teclas (debug)
                    try:
                        import time as _t
                        if _t.time() <= getattr(sys, '_mt2guide_keytrace_until', 0.0):
                            _g_log('[keytrace] tecla=%s (OnKeyDown)' % key)
                    except:
                        pass
                    # modo pesquisa (quest line aberta) come primeiro
                    try:
                        sk = getattr(sys, '_mt2guide_searchkey', None)
                        if sk is not None and sk(key):
                            return
                    except:
                        pass
                    # INSERT ou F7 -> abre/fecha o guia
                    if key in (getattr(app, 'DIK_INSERT', 210),
                               getattr(app, 'DIK_F7', 65)):
                        tg = getattr(sys, '_mt2guide_toggle', None)
                        if tg is not None:
                            _g_kw_log('INSERT/F7')
                            tg()
                            return
                    # N ou F8 -> abre/fecha a quest line
                    if key in (getattr(app, 'DIK_N', 49),
                               getattr(app, 'DIK_F8', 66)):
                        nt = getattr(sys, '_mt2guide_ntoggle', None)
                        if nt is not None:
                            _g_kw_log('N/F8')
                            nt()
                            return
                except:
                    pass
                try:
                    return _orig(key)
                except:
                    return None
            setattr(player, 'OnKeyDown', _g_onkey)
            _g_kw_ref[0] = _g_onkey
            _g_log('[keys] OnKeyDown wrap INSTALADO (metodo MT2Robs)')
        except Exception as e:
            _g_log('[keys] OnKeyDown wrap ERR: %r' % e)

    _g_install_kwrap()
    sys._mt2guide_rearm = _g_install_kwrap

    _g_log('[MT2Guide] loader ok')
