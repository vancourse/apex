# kit/template is an app template, not this repo's tests: its test files import a
# package (`__app__`) that only exists once `rails new` substitutes the name.
# tests/kit/test_kit.py generates the template and runs ITS suite in place.
collect_ignore = ["template"]
