#!/bin/bash
env $(cat .env.carnegie | xargs) python src/utils/view_table.py 