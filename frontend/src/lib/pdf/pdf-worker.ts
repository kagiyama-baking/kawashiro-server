/**
 * pdf.js のWorker URLを設定する副作用ファイル。
 *
 * Vite/Vitestの `?url` クエリでWorkerファイルのパスだけを取得し、
 * GlobalWorkerOptions に設定する。エントリ側（PdfEditPage）でこのファイルを
 * `import` するとモジュール初回ロード時に1度だけ実行される。
 *
 * 単体テストではこのモジュール自体を vi.mock してWorker起動を回避する。
 */
import * as pdfjsLib from 'pdfjs-dist';
import workerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

pdfjsLib.GlobalWorkerOptions.workerSrc = workerSrc;
