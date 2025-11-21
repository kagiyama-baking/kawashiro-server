#!/usr/bin/env python
"""テスト実行スクリプト"""
import os
import sys
import subprocess


def run_tests():
    """テストを実行"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_api.settings')

    # テストコマンドのベース
    base_command = ['pytest']

    # 引数を追加
    args = sys.argv[1:] if len(sys.argv) > 1 else ['tests', '-v']

    # テストコマンドを実行
    command = base_command + args
    print(f"Running: {' '.join(command)}")

    result = subprocess.run(command, cwd=os.path.dirname(__file__))
    sys.exit(result.returncode)


def run_coverage():
    """カバレッジ付きでテストを実行"""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_api.settings')

    # カバレッジコマンド
    command = [
        'pytest',
        'tests',
        '--cov=user',
        '--cov=onedrive',
        '--cov=core',
        '--cov-report=term-missing',
        '--cov-report=html'
    ]

    print(f"Running: {' '.join(command)}")
    result = subprocess.run(command, cwd=os.path.dirname(__file__))

    if result.returncode == 0:
        print("\nカバレッジレポートが生成されました: htmlcov/index.html")

    sys.exit(result.returncode)


def run_specific_test():
    """特定のテストを実行"""
    if len(sys.argv) < 2:
        print("使用方法: python run_tests.py specific <test_path>")
        sys.exit(1)

    test_path = sys.argv[2] if len(sys.argv) > 2 else 'tests'
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_api.settings')

    command = ['pytest', test_path, '-v', '--tb=short']
    print(f"Running: {' '.join(command)}")

    result = subprocess.run(command, cwd=os.path.dirname(__file__))
    sys.exit(result.returncode)


def main():
    """メイン関数"""
    if len(sys.argv) > 1:
        if sys.argv[1] == 'coverage':
            run_coverage()
        elif sys.argv[1] == 'specific':
            run_specific_test()
        else:
            run_tests()
    else:
        run_tests()


if __name__ == '__main__':
    main()