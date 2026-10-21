import hashlib,json,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from create_portable_zip import create_archive,verify_archive


class PortableArchiveTests(unittest.TestCase):
    def test_linux_paths_preserve_manifest_native_source_and_detect_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder=root/'package';(folder/'native').mkdir(parents=True)
            source=b'actual native source\n';(folder/'native/car_video.c').write_bytes(source)
            manifest={'runtime_files':{},'artifacts':{},'wireless_files':{
                'native/car_video.c':hashlib.sha256(source).hexdigest()}}
            (folder/'lab_manifest.json').write_text(json.dumps(manifest))
            archive=root/'portable.zip';self.assertEqual(create_archive(folder,archive),2)
            with zipfile.ZipFile(archive) as z:
                self.assertEqual([i.orig_filename for i in z.infolist()],['lab_manifest.json','native/car_video.c'])
                self.assertEqual(z.read('native/car_video.c'),source)
            with self.assertRaises(FileExistsError):create_archive(folder,archive)
            broken=root/'broken.zip'
            with zipfile.ZipFile(broken,'x') as z:
                z.writestr('lab_manifest.json',json.dumps(manifest));z.writestr('native/car_video.c',b'wrong')
            with self.assertRaisesRegex(ValueError,'mismatch'):verify_archive(broken)

    def test_windows_backslash_members_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive=Path(temporary)/'windows.zip'
            with zipfile.ZipFile(archive,'x') as z:
                info=zipfile.ZipInfo('native/car_video.c')
                info.filename=info.orig_filename='native\\car_video.c'
                z.writestr(info,b'payload')
            with self.assertRaisesRegex(ValueError,'nonportable'):verify_archive(archive)
