#!/usr/bin/env bash

CPU=$(printf "CPU:%2.0f%%" $(top -bn1 | grep "Cpu(s)" | awk '{print $2 + $4}'))
MEM=$(free | awk '/Mem/ {printf "MEM:%2.0f%", $3/$2 * 100.0}')
TIME=$(date +'%Y-%m-%d %H:%M')
printf "%s | %s | %s" "$CPU" "$MEM" "$TIME"
