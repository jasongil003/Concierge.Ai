#!/usr/bin/perl
use strict;
use warnings;
use Fcntl qw(:flock);
use File::Basename qw(dirname);
use File::Path qw(make_path);
use JSON::PP qw(encode_json decode_json);
use IO::Handle;
use Fcntl qw(F_GETFD F_SETFD FD_CLOEXEC);
use POSIX qw(strftime);

shift @ARGV eq 'run' or die "Usage: operation_lock.pl run --lock PATH -- COMMAND...\n";
my $lock_path;
while (@ARGV) {
    my $argument = shift @ARGV;
    last if $argument eq '--';
    if ($argument eq '--lock') {
        $lock_path = shift @ARGV;
    } else {
        die "Unknown argument.\n";
    }
}
defined $lock_path && length $lock_path or die "--lock PATH is required.\n";
@ARGV or die "A command is required after --.\n";
make_path(dirname($lock_path));
open my $lock, '+>>', $lock_path or die "Could not open deployment lock.\n";
unless (flock($lock, LOCK_EX | LOCK_NB)) {
    seek($lock, 0, 0);
    local $/;
    my $metadata = eval { decode_json(<$lock> // '') } || {};
    my $pid = $metadata->{pid} // 'unknown';
    my $started = $metadata->{started_at} // 'unknown';
    print STDERR "Another Concierge.AI deployment operation is running. PID: $pid. Started: $started.\n";
    exit 2;
}
my $record = {
    pid => $$,
    started_at => strftime('%Y-%m-%dT%H:%M:%SZ', gmtime()),
};
seek($lock, 0, 0);
truncate($lock, 0) or die "Could not update deployment lock metadata.\n";
print {$lock} encode_json($record), "\n" or die "Could not write deployment lock metadata.\n";
$lock->flush() or die "Could not flush deployment lock metadata.\n";
my $fd_flags = fcntl($lock, F_GETFD, 0);
defined $fd_flags && fcntl($lock, F_SETFD, $fd_flags & ~FD_CLOEXEC)
    or die "Could not preserve the deployment lock across exec.\n";
$ENV{CONCIERGE_OPERATION_LOCK_HELD} = '1';
exec { $ARGV[0] } @ARGV;
die "Could not start deployment command.\n";
