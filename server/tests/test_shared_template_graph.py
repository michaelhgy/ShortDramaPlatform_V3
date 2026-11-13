import unittest
from server.ffmpeg_templates.shared_graph import share,tokens


class SharedGraphTests(unittest.TestCase):
    def test_identical_input_and_preparation_share_one_result_with_fanout(self):
        inputs=['-i','same.mkv','-i','same.mkv']
        graph='[0:v]format=rgba[a];[1:v]format=rgba[b];[a][b]hstack=inputs=2[out]'
        args,g,stats=share(inputs,graph)
        self.assertEqual(args,['-threads','2','-i','same.mkv'])
        self.assertEqual(stats['inputs_after'],1);self.assertEqual(stats['chains_after'],2)
        self.assertEqual(g.count('format=rgba'),1);self.assertIn('split=2',g)
        self.assertIn('hstack=inputs=2',g)

    def test_seek_and_loop_options_distinguish_inputs(self):
        inputs=['-ss','1','-i','same.mkv','-ss','2','-i','same.mkv']
        _,_,stats=share(inputs,'[0:v]null[a];[1:v]null[b];[a][b]hstack[out]')
        self.assertEqual(stats['inputs_after'],2)

    def test_named_and_stateful_filters_are_not_folded(self):
        for effect in ['noise=all_seed=123','blend@fade=all_opacity=0.5']:
            ins='[0:v][0:v]' if effect.startswith('blend') else '[0:v]'
            graph=f'{ins}{effect}[a];{ins}{effect}[b];[a][b]hstack[out]'
            _,g,stats=share(['-i','same'],graph)
            self.assertEqual(g.count(effect),2);self.assertEqual(stats['chains_after'],3)

    def test_phase_differences_remain_independent(self):
        graph='[0:v]trim=start_frame=3,setpts=N[a];[1:v]trim=start_frame=4,setpts=N[b];[a][b]hstack[out]'
        _,g,stats=share(['-i','same','-i','same'],graph)
        self.assertEqual(stats['inputs_after'],1);self.assertEqual(stats['chains_after'],3)
        self.assertIn('start_frame=3',g);self.assertIn('start_frame=4',g)

    def test_multiple_outputs_can_share_their_children(self):
        graph='[0:v]split=2[a][b];[a]crop=10:10:0:0[al];[b]crop=10:10:0:10[bl];[1:v]split=2[c][d];[c]crop=10:10:0:0[cl];[d]crop=10:10:0:10[dl];[al][bl][cl][dl]hstack=inputs=4[out]'
        _,g,stats=share(['-i','same','-i','same'],graph)
        self.assertEqual(stats['chains_after'],4)
        self.assertEqual(g.count('crop=10:10:0:0'),1)

    def test_quotes_and_escapes_do_not_split_filters(self):
        self.assertEqual(tokens("lut=y='if(lt(val,2),3,4)',format=gray",','),["lut=y='if(lt(val,2),3,4)'",'format=gray'])
        self.assertEqual(tokens(r"sendcmd=f='C\:/one;two.txt';null",';'),[r"sendcmd=f='C\:/one;two.txt'",'null'])
        self.assertEqual(tokens(r'scale=x\,y,format=rgb',','),[r'scale=x\,y','format=rgb'])

    def test_explicit_thread_setting_is_preserved(self):
        args,_,_=share(['-threads','4','-i','source'],'[0:v]null[out]')
        self.assertEqual(args,['-threads','4','-i','source'])

    def test_sticker_seek_never_combines_seek_with_infinite_loop(self):
        from server.ffmpeg_templates.precompose import sticker_stream
        for phase in (0,1,2,299,615,898,899):
            args,g=sticker_stream('cache.mkv',phase,1800)
            pending=[]
            for arg in args:
                pending.append(str(arg))
                if arg=='cache.mkv':
                    self.assertFalse('-ss' in pending and '-stream_loop' in pending)
                    pending=[]
            self.assertIn('[packedstick]',g)

    def test_sticker_short_suffix_does_not_open_unneeded_loop(self):
        from server.ffmpeg_templates.precompose import sticker_stream
        args,g=sticker_stream('cache.mkv',615,30)
        self.assertEqual(args.count('-i'),1)
        self.assertNotIn('concat',g)

    def test_region_graph_uses_saved_heights_and_keeps_fallback_for_overlap(self):
        from server.ffmpeg_templates.precompose import base_graph
        p={'frames':5400,'tracks':[{'height':540},{'height':688}],
           'stickers':{'start_frame':600},'config':{'sticker_alpha_percent':80}}
        c={'scenery':[{'video':'top.mp4','mask':'top.png'},{'video':'bottom.mp4','mask':'bottom.png'}],'stickers':'cache.mkv'}
        args,g=base_graph(p,c,1815,870,'black')
        self.assertIn('s=1080x540',g);self.assertIn('s=1080x688',g)
        self.assertIn('s=1080x1172',g);self.assertIn('overlay=0:208:',g)
        self.assertEqual(args.count('-i'),6)
        p['tracks']=[{'height':1300},{'height':1300}]
        _,g=base_graph(p,c,0,30,'black')
        self.assertIn('s=1080x2400',g);self.assertNotIn('vstack',g)

    def test_sliced_transition_keeps_command_order_and_exact_output_length(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from unittest.mock import patch
        from server.ffmpeg_templates.precompose import compile_piece
        # sendcmd mutates blend opacity; partial seams must not share/reorder
        # upstream work, even when the inputs appear identical.
        graph='[0:v]sendcmd=f=fade.txt[a];[a][1:v]blend@fade=all_mode=normal[out]'
        with TemporaryDirectory() as folder:
            renderer=SimpleNamespace(folder=Path(folder),encoder='h264_nvenc',cache_encoder='h264_nvenc')
            with patch('server.ffmpeg_templates.precompose.read',return_value={'assets':[]}), \
                 patch('server.ffmpeg_templates.precompose.transfer_graph',return_value=(['-i','same','-i','same'],graph)), \
                 patch('server.ffmpeg_templates.precompose.Pipeline') as pipeline, \
                 patch('server.ffmpeg_templates.shared_graph.share') as sharing:
                compile_piece(renderer,{}, {}, {'start':5385,'end':5415,'cache_trim':[0,15],'segments':[]},'tail')
                sharing.assert_not_called()
                args=pipeline.return_value.command.call_args.args[1]
                self.assertEqual(args.count('-i'),2)
                self.assertEqual(args[args.index('-frames:v')+1],15)
                result=(Path(folder)/'tail.ffgraph').read_text()
                self.assertTrue(result.startswith(graph.replace('[out]','[uncut]')))


if __name__=='__main__':unittest.main()
