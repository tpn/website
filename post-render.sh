#!/bin/sh

rsync -av --ignore-existing static/ docs
