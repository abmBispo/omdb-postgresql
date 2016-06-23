#!/usr/bin/perl

use strict;
use warnings;
use CGI;
use CGI::Carp qw(fatalsToBrowser warningsToBrowser);
use DBD::Pg;
use Template;

binmode STDOUT, ':encoding(UTF-8)';

my $directory = readlink ($0) || $0;
$directory =~ s!/[^/]+$!!;

my $dbh = DBI->connect("dbi:Pg:dbname=omdb client_encoding=UTF-8", '', '',
	{ AutoCommit => 0, RaiseError => 1, PrintError => 0 });

# create Template object
my $template = Template->new(
	INCLUDE_PATH => "$directory/templates",
	PRE_PROCESS => "header",
	POST_PROCESS => "footer",
	INTERPOLATE => 1, # expand "$var" in plain text
	POST_CHOMP => 1, # weed whitespace
);

# create CGI object
my $q = CGI->new;
my $path = $q->path_info();

print $q->header(
	-type => 'text/html',
	-charset => 'utf-8',
);

sub error ($)
{
	my $error = shift;
	$template->process('error', {
		title => "Error: $error",
		error => $error,
	}) || die $template->error();
	exit;
}

sub selectall_hashrows
{
	my $sth = $dbh->prepare(shift);
	$sth->execute(@_);
	my @rows;
	while (my $row = $sth->fetchrow_hashref()) {
		push @rows, $row;
	}
	return \@rows;
}

sub process
{
	my ($t, $vars) = @_;
	my $output;
	$template->process ($t, $vars, \$output)
		|| die $template->error();
	print $output;
}

if ($path =~ m!^/movie/(\d+)!) {
	my $movie_id = $1;

	my $movie = $dbh->selectrow_hashref("SELECT * FROM movies WHERE id = ?", undef, $movie_id)
		or error ("Movie ID $movie_id is unknown");
	my $series = $movie->{series_id} &&
		$dbh->selectrow_hashref("SELECT * FROM movies WHERE id = ?", undef, $movie->{series_id});
	my $parent = $movie->{parent_id} &&
		$dbh->selectrow_hashref("SELECT * FROM movies WHERE id = ?", undef, $movie->{parent_id});
	my $child_movies = selectall_hashrows("SELECT * FROM movies WHERE parent_id = ? ORDER BY date", $movie_id);
	my $episodes = selectall_hashrows("SELECT * FROM movies WHERE series_id = ? ORDER BY date", $movie_id);

	my $cast = selectall_hashrows("SELECT *, p.name AS person_name, j.name AS job_name FROM people p JOIN casts c ON (p.id = c.person_id) JOIN jobs j ON (c.job_id = j.id) WHERE c.movie_id = ? ORDER BY c.position, j.name, p.name", $movie_id);

	process('movie', {
		title => "$movie->{name} ($movie->{kind})",
		movie => $movie,
		movie_details =>
			$dbh->selectrow_hashref("SELECT * FROM movie_details WHERE movie_id = ?", undef, $movie_id),
		votes =>
			$dbh->selectrow_hashref("SELECT * FROM votes WHERE movie_id = ?", undef, $movie_id),
		series => $series,
		parent => $parent,
		child_movies => $child_movies,
		episodes => $episodes,
		countries =>
			$dbh->selectcol_arrayref("SELECT country FROM movie_countries WHERE movie_id = ?", undef, $movie_id),
		abstract_de =>
			$dbh->selectrow_hashref("SELECT * FROM movie_abstracts_de WHERE movie_id = ?", undef, $movie_id),
		abstract_en =>
			$dbh->selectrow_hashref("SELECT * FROM movie_abstracts_en WHERE movie_id = ?", undef, $movie_id),
		trailers =>
			selectall_hashrows("SELECT * FROM trailers WHERE movie_id = ? ORDER BY language, trailer_id", $movie_id),
		cast => $cast,
		references_to =>
			selectall_hashrows("SELECT * FROM movie_references r JOIN movies m ON (r.referenced_id = m.id) WHERE movie_id = ? ORDER BY type, date", $movie_id),
		references_from =>
			selectall_hashrows("SELECT * FROM movie_references r JOIN movies m ON (r.movie_id = m.id) WHERE referenced_id = ? ORDER BY type, date", $movie_id),
		links =>
			selectall_hashrows("SELECT * FROM movie_links WHERE movie_id = ? ORDER BY source, key, language", $movie_id),
		categories =>
			selectall_hashrows("SELECT c.* FROM categories c JOIN movie_categories m ON (c.id = m.category_id) WHERE m.movie_id = ? ORDER BY c.name", $movie_id),
	});

} elsif ($path =~ m!^/person/(\d+)!) {
	my $person_id = $1;

	my $person = $dbh->selectrow_hashref("SELECT * FROM people WHERE id = ?", undef, $person_id)
		or error ("Person ID $person_id is unknown");

	my $movies = selectall_hashrows("SELECT *, m.name AS movie_name, j.name AS job_name FROM movies m JOIN casts c ON (m.id = c.movie_id) JOIN jobs j ON (c.job_id = j.id) WHERE c.person_id = ? ORDER BY m.date", $person_id);

	process('person', {
		title => "$person->{name}",
		person => $person,
		movies => $movies,
		links =>
			selectall_hashrows("SELECT * FROM people_links WHERE person_id = ? ORDER BY source, key, language", $person_id),
	});

} elsif ($path =~ m!^/category/(\d+)!) {
	my $category_id = $1;

	my $category = $dbh->selectrow_hashref("SELECT * FROM categories WHERE id = ?", undef, $category_id)
		or error ("Category ID $category_id is unknown");

	process('category', {
		title => "$category->{name}",
		category => $category,
		movies => selectall_hashrows("SELECT m.* FROM movies m JOIN movie_categories c ON (m.id = c.movie_id) WHERE c.category_id = ? ORDER BY m.date", $category_id),
	});

} elsif ($path =~ m!^/country/(\w+)!) {
	my $country = $1;

	process('country', {
		title => "Movies from $country",
		movies => selectall_hashrows("SELECT m.* FROM movies m JOIN movie_countries c ON (m.id = c.movie_id) WHERE c.country = ? ORDER BY m.date", $country),
	});

} elsif ($path =~ m!^/job/(\d+)!) {
	my $job_id = $1;

	my $job = $dbh->selectrow_hashref("SELECT * FROM jobs WHERE id = ?", undef, $job_id)
		or error ("Job ID $job_id is unknown");

	process('job', {
		title => "$job->{name}",
		people => selectall_hashrows("SELECT person_id, p.name, COUNT(*) FROM people p JOIN casts c ON (p.id = c.person_id) WHERE c.job_id = ? GROUP BY person_id, p.name ORDER BY p.name LIMIT 10000", $job_id),
	});

} elsif ($path =~ m!^/?$!) {
	process('main', {
		title => "OMDB",
		script_name => $ENV{SCRIPT_NAME},
		movies => selectall_hashrows("SELECT * FROM movies p ORDER BY random() LIMIT 10"),
		people => selectall_hashrows("SELECT * FROM people p ORDER BY random() LIMIT 10"),
	});

} else {
	print "<pre>";
	print "$_: $ENV{$_}\n" foreach (sort keys %ENV);
	print "</pre>";
	error ("404 - Path $path unknown");
}