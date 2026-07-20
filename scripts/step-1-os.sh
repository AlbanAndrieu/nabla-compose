#!/bin/bash
case "$OSTYPE" in
linux*) export SYSTEM=LINUX;;
darwin*) export SYSTEM=OSX;;
win*) export SYSTEM=Windows;;
cygwin*) export SYSTEM=Cygwin;;
msys*) export SYSTEM=MSYS;;
bsd*) export SYSTEM=BSD;;
solaris*) export SYSTEM=SOLARIS;;
*) export SYSTEM=UNKNOWN
esac
echo "SYSTEM : $SYSTEM"
if [ -f /etc/os-release ];then
  . /etc/os-release
  OS=$NAME
  VER=$VERSION_ID
elif type lsb_release > /dev/null 2>&1;then
  OS=$(lsb_release -si)
  VER=$(lsb_release -sr)
elif [ -f /etc/lsb-release ];then
  . /etc/lsb-release
  OS=$DISTRIB_ID
  VER=$DISTRIB_RELEASE
elif [ -f /etc/debian_version ];then
  OS=Debian
  VER=$(cat /etc/debian_version)
elif [ -f /etc/SuSe-release ];then
  ...
elif [ -f /etc/redhat-release ];then
  OS=$(uname -s)
  VER=$(uname -r)
else
  OS=$(uname -s)
  VER=$(uname -r)
fi
echo "OS : $OS"
echo "VER : $VER"
