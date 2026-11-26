Changelog
---------

*unreleased*
~~~~~~~~~~~~

Removals:

* Drop support for EOL Python 3.9. (:pull:`1354`)

Features:

* Add :func:`~packaging.markers.prepare_environment` and
  :meth:`Marker.evaluate_prepared() <packaging.markers.Marker.evaluate_prepared>`
  to evaluate many markers against one prepared environment.
  ``Pylock.select()`` now uses them. (:pull:`1469`)
* Add ``__replace__`` to :class:`~packaging.requirements.Requirement`,
  :class:`~packaging.specifiers.Specifier`, and
  :class:`~packaging.specifiers.SpecifierSet`, for ``copy.replace()`` on
  Python 3.13+. (:pull:`1377`, :pull:`1457`)
* Add :meth:`VersionRange.from_bounds() <packaging.ranges.VersionRange.from_bounds>`
  to make a range from explicit bounds. (:pull:`1475`)
* Add :meth:`VersionRange.snap_bounds() <packaging.ranges.VersionRange.snap_bounds>`
  to move range endpoints onto known versions. (:pull:`1477`)
* Add :meth:`VersionRange.relation() <packaging.ranges.VersionRange.relation>`
  and :class:`~packaging.ranges.RangeRelation`, which give containment and
  disjointness in one pass. (:pull:`1473`)
* Add :func:`~packaging.tags.interpreter_abi`. (:pull:`611`)
* ``Marker.evaluate()`` accepts a set of names for ``extra``, to evaluate
  a marker against several selected extras at once. (:pull:`1438`)
* Add ``message``, ``source``, and ``span`` attributes to
  :class:`~packaging.requirements.InvalidRequirement` and
  :class:`~packaging.markers.InvalidMarker` for syntax errors. (:pull:`1547`, :pull:`1554`)

Behavior adaptations:

* ``str()`` of markers joined with ``&`` or ``|`` has fewer parentheses when
  unambiguous. Evaluation and parsed markers do not change. (:pull:`1510`)
* The ``pylock`` and ``direct_url`` dataclasses use ``__slots__``.  Pickles
  from 26.3 still load. (:pull:`1366`, :pull:`1548`)
* ``Version.__replace__()`` raises ``TypeError`` for unknown keyword arguments
  instead of ignoring them. (:pull:`1378`)

Fixes for versions and specifiers:

* Parse plain strings in the iterable form of ``SpecifierSet``, and raise
  ``TypeError`` for elements that are not ``Specifier`` or ``str``.
  (:pull:`1485`)
* Reject an empty arbitrary-equality version (``===``) in specifiers and
  requirements. (:pull:`1430`)
* Reject non-ASCII letters in ``~=`` pre, post, and dev segments.
  (:pull:`1384`)
* Keep the explicit pre-release opt-in of a literal pre-release version that
  overlaps an ordinary bound in a ``VersionRange``. (:pull:`1511`)
* Support ``copy`` and ``pickle`` for ``VersionRange``, which raised
  ``TypeError`` before. (:pull:`1504`)

Fixes for requirements and markers:

* Reject all whitespace in the URL of a requirement, including Unicode
  whitespace such as a no-break space. (:pull:`1379`)
* Parse ``===`` followed by a comma and a spaced specifier in a requirement.
  (:pull:`1531`)
* Keep the ``prereleases`` override of each specifier when a ``Requirement``
  is pickled or copied. (:pull:`1462`)
* Raise ``InvalidMarker`` for markers nested more than 200 levels deep.
  (:pull:`1450`)
* Keep chains of ``&`` and ``|`` on markers flat, so long chains do not
  raise. (:pull:`1510`)
* ``Marker.evaluate()`` raises ``UndefinedComparison`` when ``extras`` or
  ``dependency_groups`` is a string instead of a set. (:pull:`1507`)

Fixes for metadata and licenses:

* Validate and serialize inherited fields in ``Metadata`` subclasses.
  (:pull:`1454`)
* Reject Windows drive-relative ``License-File`` paths like ``C:LICENSE``.
  (:pull:`1382`)
* Use one spelling, the first one, for case variants of a ``LicenseRef-``
  identifier in ``canonicalize_license_expression()``. (:pull:`1412`)
* Reject non-ASCII ``LicenseRef-`` identifiers before normalization.
  (:pull:`1481`)

Fixes for tags and filenames:

* Reject wheel build tags that contain a line break. (:pull:`1427`)
* Keep explicitly empty ``platforms`` iterables in ``cpython_tags()``,
  ``generic_tags()``, and ``compatible_tags()`` instead of using the host
  platforms. (:pull:`1360`)
* Detect free-threaded builds in ``cpython_tags()`` when a generic ABI such
  as ``abi3`` or ``none`` comes first in ``abis``, or when ``abis`` holds
  only ``abi3t``. (:pull:`1555`)

Fixes for pylock and dependency groups:

* ``Pylock.select()`` raises ``PylockSelectError`` for an explicitly empty
  ``environments`` list (:pull:`1362`), and for unknown extras and
  dependency groups. (:pull:`1376`)
* Get ``pylock`` file names from paths with mixed Windows path separators.
  (:pull:`1436`)
* Require the complete file name to match in ``is_valid_pylock_path()``.
  (:pull:`1446`)
* Reject pre-releases of ``lock-version`` 2, such as ``2.0rc1``.
  (:pull:`1522`)
* Collect errors from all includes in dependency groups, including sibling
  includes after a parse error and includes in malformed groups, and report
  each failing group once. (:pull:`1411`, :pull:`1439`, :pull:`1492`)
* Name the correct group when a dependency group includes itself with a
  different spelling. (:pull:`1519`)

Performance:

* Support lazy imports on Python 3.15+. (:pull:`1129`)
* Cache the canonical form of a ``Specifier``. (:pull:`1372`)
* Speed up and cache ``str(Marker)``. (:pull:`1371`, :pull:`1459`)
* Avoid ``literal_eval`` for plain marker strings. (:pull:`1429`)
* Speed up ``VersionRange`` construction, subtraction, comparison,
  disjointness checks, membership checks, and filtering. (:pull:`1458`,
  :pull:`1460`, :pull:`1471`, :pull:`1506`, :pull:`1542`, :pull:`1551`,
  :pull:`1556`, :pull:`1558`, :pull:`1562`, :pull:`1563`, :pull:`1564`,
  :pull:`1568`)
* Speed up ``Version`` parsing, string conversion, and release validation.
  (:pull:`1520`, :pull:`1523`, :pull:`1524`, :pull:`1538`)
* Speed up ``Specifier`` parsing, string conversion, hashing, and equality.
  (:pull:`1529`, :pull:`1544`, :pull:`1571`)
* Speed up ``Specifier.contains()`` for simple comparisons. (:pull:`1536`)
* Speed up marker and requirement parsing. (:pull:`1494`, :pull:`1495`,
  :pull:`1525`, :pull:`1545`)
* Validate license expressions without compiling Python code.
  (:pull:`1527`)

Documentation:

* Add a GitHub link next to the page icons. (:pull:`1444`)
* Use autodoc for the ``pylock`` and ``requirements`` API reference
  (:pull:`1393`), and for ``packaging.tags.INTERPRETER_SHORT_NAMES``.
  (:pull:`1491`)
* Fix duplicated words in comments and docstrings. (:pull:`1516`)
* Update the contribution guide for batched changelog edits and remove
  PyPy 3.9 from the nox example. (:pull:`1383`, :pull:`1456`)

Benchmarks:

* Add Python 3.15 to the benchmarks. (:pull:`1380`)
* Add ``VersionRange`` and PubGrub resolver benchmarks. (:pull:`1541`,
  :pull:`1543`, :pull:`1570`)
* Report benchmark changes in a summary table and as PR comments.
  (:pull:`1526`, :pull:`1528`)
* Make the cold benchmarks independent of internal caches, and do not filter
  compatible release examples in tests. (:pull:`1407`, :pull:`1508`)

Internal:

* Modernize the code for Python 3.10. (:pull:`1347`, :pull:`1365`,
  :pull:`1367`, :pull:`1368`, :pull:`1369`)
* Give an unbounded end of a range one spelling, so that it compares and
  hashes the same. (:pull:`1392`)
* Remove unused constants in ``metadata``. (:pull:`1488`)
* Speed up the test suite. (:pull:`1385`, :pull:`1386`, :pull:`1387`,
  :pull:`1388`, :pull:`1389`, :pull:`1390`, :pull:`1391`)
* Support parallel nox sessions. (:pull:`1381`)
* Simplify the cached spec ``Version`` in ``Specifier``. (:pull:`1539`)
* Update the downstream test projects. (:pull:`1400`, :pull:`1479`,
  :pull:`1490`, :pull:`1493`)
* Type the marker tree and parser return values precisely. (:pull:`1513`,
  :pull:`1517`)
* Skip GC freezing for property tests, and cover overlapping pre-release
  literals in ranges. (:pull:`1514`, :pull:`1515`)
* Test that pickles from 26.2 and 26.3 load, including ``pylock`` and
  ``direct_url`` objects. (:pull:`1550`)
* Update CI: test feature branches, always run lint, check all test jobs,
  set up in parallel, and pin the oldest Python jobs to Ubuntu 24.04.
  (:pull:`1355`, :pull:`1414`, :pull:`1423`, :pull:`1441`, :pull:`1442`,
  :pull:`1443`, :pull:`1463`)
* Update GitHub Actions and pre-commit hooks. (:pull:`1401`, :pull:`1402`,
  :pull:`1432`, :pull:`1433`, :pull:`1483`, :pull:`1484`)

26.3 - 2026-08-03
~~~~~~~~~~~~~~~~~

Features:

* Add a public :class:`~packaging.ranges.VersionRange` API and
  :meth:`SpecifierSet.to_range() <packaging.specifiers.SpecifierSet.to_range>`,
  representing the versions a specifier set accepts as an interval set that
  supports intersection, union, difference, complement, set relations,
  membership tests, and filtering.
  :meth:`~packaging.ranges.VersionRange.to_specifier_set` converts a range back
  to a :class:`~packaging.specifiers.SpecifierSet` where a PEP 440 form exists.
  (:pull:`1267`, :pull:`1270`, :pull:`1298`)
* PEP 808: accept ``Metadata-Version: 2.6``. (:pull:`1194`)
* Add a ``limit`` argument to ``parse_tag()`` for compressed tag sets.
  (:issue:`1220`)
* Add a ``prefer_sdist_predicate`` argument to ``Pylock.select()`` to prefer
  source distributions over wheels for selected packages. (:pull:`1334`)
* Add :func:`~packaging.tags.pure_python_tags` to generate the pure-Python
  tags for a Python version without touching the running platform.
  (:pull:`1346`)
* Add :meth:`SpecifierSet.is_subset()
  <packaging.specifiers.SpecifierSet.is_subset>`, :meth:`~packaging.specifiers.SpecifierSet.is_superset`,
  and :meth:`~packaging.specifiers.SpecifierSet.is_disjoint`, which compare the
  versions two specifier sets accept. (:pull:`1313`)

Behavior adaptations:

* Drop support for Python 3.8; packaging now requires Python 3.9 or later.
  (:pull:`1157`)
* Prefer native ``linux_*`` platform tags over ``manylinux`` and ``musllinux``
  tags on Linux. (:issue:`160`)

Fixes for versions and specifiers:

* Raise ``InvalidVersion`` instead of ``TypeError`` when ``Version`` is given a
  non-string. (:pull:`1319`)
* Raise ``InvalidVersion`` for non-string pre-release letters passed to
  ``Version.from_parts``. (:pull:`1241`)
* Fix an ``AttributeError`` when hashing internally trimmed versions.
  (:pull:`1242`)
* Fix ``SpecifierSet.is_unsatisfiable`` for post-release boundary
  intersections. (:pull:`1257`)

Fixes for requirements and markers:

* Make ``Requirement.__hash__`` consistent with ``__eq__`` for
  trailing-zero-equivalent specifiers (e.g. ``foo==1.0.0`` and
  ``foo==1.0.0.0``), so equal requirements hash equal and deduplicate in
  sets and dicts. (:pull:`1232`)
* Normalize requested extra names before comparing or hashing requirements.
  (:issue:`644`)
* Preserve a ``Requirement``'s specifier ``prereleases`` override across a
  pickle round trip. (:issue:`1204`)
* Raise ``InvalidRequirement`` instead of ``InvalidSpecifier`` when a
  requirement contains an invalid specifier. (:pull:`1332`)
* Clarify the error for post-release prefix wildcards like ``==1.0.post1.*``.
  (:pull:`1299`)
* Preserve quoting semantics when serializing marker values, so round-tripped
  markers parse back to the same marker. (:pull:`1213`)
* Keep the parentheses of a nested group when serializing markers.
  (:pull:`1316`)
* Normalize ``extra`` and ``dependency_groups`` values in nested markers at
